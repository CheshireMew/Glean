"""Bounded launcher logs; retention reports candidates and never deletes them."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import uuid


class LogBudgetError(RuntimeError):
    pass


@dataclass(frozen=True)
class LogPolicy:
    file_bytes: int = 2 * 1024 * 1024
    total_bytes: int = 128 * 1024 * 1024
    max_runs: int = 20
    retention_days: int = 14

    @classmethod
    def from_env(cls, env):
        values = {
            'file_bytes': int(env.get('GLEAN_LAUNCHER_LOG_MAX_BYTES', cls.file_bytes)),
            'total_bytes': int(env.get('GLEAN_LAUNCHER_LOG_TOTAL_BYTES', cls.total_bytes)),
            'max_runs': int(env.get('GLEAN_LAUNCHER_LOG_MAX_RUNS', cls.max_runs)),
            'retention_days': int(env.get('GLEAN_LAUNCHER_LOG_RETENTION_DAYS', cls.retention_days)),
        }
        if values['file_bytes'] < 1024 or any(value <= 0 for value in values.values()):
            raise LogBudgetError('日志预算必须为正数，单文件至少 1024 字节')
        return cls(**values)


class BoundedLogWriter:
    def __init__(self, path: Path, max_bytes: int, identity: str):
        self.header = (identity + '\n').encode('utf-8')[:min(512, max_bytes // 4)]
        self.budget = max_bytes - len(self.header)
        self.chunks = deque()
        self.size = 0
        self.output = path.open('wb')
        self.output.write(self.header)
        self.output.flush()

    def write(self, line: str):
        value = line.encode('utf-8')
        if len(value) > self.budget:
            value = value[-self.budget:].decode('utf-8', errors='ignore').encode('utf-8')
        self.chunks.append(value)
        self.size += len(value)
        compact = False
        while self.size > self.budget:
            first = self.chunks.popleft()
            remove = min(len(first), self.size - self.budget)
            rest = first[remove:].decode('utf-8', errors='ignore').encode('utf-8')
            self.size -= len(first)
            if rest:
                self.chunks.appendleft(rest)
                self.size += len(rest)
            compact = True
        if compact:
            self.output.seek(0)
            self.output.write(self.header)
            for chunk in self.chunks:
                self.output.write(chunk)
            self.output.truncate()
        else:
            self.output.write(value)
        self.output.flush()

    def close(self):
        self.output.close()


class LogRunStore:
    OWNER = 'glean.windows.launcher/v1'

    def __init__(self, root: Path, policy: LogPolicy):
        self.root = root
        self.policy = policy

    def inspect(self):
        runs = []
        total = 0
        if self.root.exists():
            for directory in sorted(self.root.iterdir()):
                if directory.is_symlink():
                    raise LogBudgetError(f'日志目录包含链接，请人工核对：{directory.resolve()}')
                if not directory.is_dir():
                    total += directory.stat().st_size
                    continue
                files = list(directory.rglob('*'))
                if any(path.is_symlink() for path in files):
                    raise LogBudgetError(f'日志运行目录包含链接，请人工核对：{directory}')
                size = sum(path.stat().st_size for path in files if path.is_file())
                total += size
                manifest_path = directory / 'run.json'
                try:
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                except (FileNotFoundError, ValueError):
                    manifest = {}
                finished = manifest.get('finished_at')
                owned = manifest.get('owner') == self.OWNER
                expired = bool(finished and datetime.fromisoformat(finished) < datetime.now(timezone.utc) - timedelta(days=self.policy.retention_days))
                runs.append({'path': str(directory.resolve()), 'bytes': size, 'owned': owned,
                             'state': manifest.get('state', 'unknown'), 'expired': expired,
                             'cleanup_candidate': owned and bool(finished)})
        return {'root': str(self.root.resolve()), 'bytes': total, 'runs': runs,
                'policy': self.policy.__dict__, 'deletion': 'requires-user-authorization'}

    def accept(self) -> tuple[Path, dict]:
        report = self.inspect()
        # Reserve all three service logs and the small manifest before accepting
        # any child process. Old/unknown logs still count against the same budget.
        reserve = self.policy.file_bytes * 3 + 4096
        if len(report['runs']) >= self.policy.max_runs or report['bytes'] + reserve > self.policy.total_bytes or any(run['expired'] for run in report['runs']):
            paths = '\n'.join(run['path'] for run in report['runs'] if run['cleanup_candidate'])
            raise LogBudgetError(f"日志保留预算已达到上限，未启动新服务。先检查 --logs-status 并取得清理授权。\n日志根：{report['root']}\n可审查的已结束运行：\n{paths or '没有可自动确认归属的运行；旧目录需人工核对'}")
        now = datetime.now(timezone.utc)
        run_id = f'{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}'
        directory = self.root / run_id
        directory.mkdir(parents=True)
        manifest = {'owner': self.OWNER, 'run_id': run_id, 'launcher_pid': os.getpid(),
                    'started_at': now.isoformat(), 'finished_at': None, 'state': 'starting',
                    'policy': self.policy.__dict__}
        self.write(directory, manifest)
        return directory, manifest

    @staticmethod
    def write(directory: Path, manifest: dict):
        (directory / 'run.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
