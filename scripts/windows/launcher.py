"""Single-console Windows startup, real port probes, readiness and child cleanup."""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener
import uuid
import webbrowser

from process_job import ProcessJob

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTTP = build_opener(ProxyHandler({}))


class StartupError(RuntimeError):
    pass


def probe_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(1)


def select_frontend_port(candidates=None) -> tuple[int, list[tuple[int, str]]]:
    # Use the same executable and HTTP listen call as Vite, including Windows bind behavior.
    probe = """
import http from 'node:http';
const results = [];
for (const port of JSON.parse(process.argv[1])) {
  const result = await new Promise(resolve => {
    const server = http.createServer();
    server.once('error', error => resolve({ port, error: error.code }));
    server.listen(port, '127.0.0.1', () => server.close(() => resolve({ port, ok: true })));
  });
  results.push(result);
  if (result.ok) break;
}
process.stdout.write(JSON.stringify(results));
"""
    ports = tuple(candidates) if candidates is not None else (*range(5173, 5193), *range(3000, 3020))
    result = subprocess.run(
        [shutil.which("node"), "--input-type=module", "-e", probe, json.dumps(ports)],
        capture_output=True, text=True, encoding="utf-8", timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise StartupError("无法检测网页端口：" + result.stderr.strip())
    unavailable = []
    for item in json.loads(result.stdout):
        if item.get("ok"):
            return item["port"], unavailable
        reason = "Windows 拒绝访问" if item.get("error") == "EACCES" else "端口已占用或不可用"
        unavailable.append((item["port"], reason))
    raise StartupError("没有找到可用的本机网页端口")


def existing_workers() -> list[int]:
    query = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match '\\s-m\\s+backend\\.worker(?:\\s|$)' } | "
        "Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
    )
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-Command", query],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise StartupError("无法检查已有 worker，请查看本机进程状态后重试")
    data = json.loads(result.stdout.strip() or "[]")
    return data if isinstance(data, list) else [data]


def prepare(frontend_only: bool = False) -> tuple[int, dict[str, str]]:
    if os.name != "nt":
        raise StartupError("此启动器用于 Windows")
    if not shutil.which("node") or not (PROJECT_ROOT / "frontend/node_modules/vite/bin/vite.js").is_file():
        raise StartupError("未找到 Node.js 或 Vite。请安装 Node.js，并在 frontend 目录执行 npm ci")
    if not frontend_only:
        modules = ("uvicorn", "fastapi", "playwright", "bs4", "lxml", "openai", "dotenv", "httpx", "jwt", "multipart", "tzdata")
        missing = [name for name in modules if importlib.util.find_spec(name) is None]
        if missing:
            raise StartupError("缺少 Python 依赖：" + ", ".join(missing) + "；请安装 requirements.lock")
        try:
            probe_port(8000)
        except OSError as error:
            raise StartupError("后端端口 8000 已占用或被 Windows 拒绝，请先停止原服务或检查端口") from error
        workers = existing_workers()
        if workers:
            raise StartupError(f"后台任务已在运行（PID: {', '.join(map(str, workers))}），请先停止原服务")
    port, unavailable = select_frontend_port()
    if unavailable:
        print(f"端口 {unavailable[0][0]} {unavailable[0][1]}，网页改用 {port}。", flush=True)
    env = os.environ.copy()
    if importlib.util.find_spec("dotenv"):
        from dotenv import dotenv_values
        for key, value in dotenv_values(PROJECT_ROOT / ".env.development").items():
            if value is not None:
                env.setdefault(key, value)
    env.update(GLEAN_ENV="development", PYTHONUTF8="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
    origins = [value.strip() for value in env.get("ALLOWED_ORIGINS", "").split(",") if value.strip()]
    for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
        if origin not in origins:
            origins.append(origin)
    env["ALLOWED_ORIGINS"] = ",".join(origins)
    site = env.get("PUBLIC_SITE_URL", "")
    if not site or urlparse(site).hostname in ("localhost", "127.0.0.1"):
        env["PUBLIC_SITE_URL"] = f"http://127.0.0.1:{port}"
    return port, env


@dataclass
class Service:
    name: str
    process: subprocess.Popen
    log_path: Path
    tail: deque = field(default_factory=lambda: deque(maxlen=18))
    reader: threading.Thread | None = None

    def collect(self):
        with self.log_path.open("w", encoding="utf-8", buffering=1) as output:
            for line in self.process.stdout:
                output.write(line)
                self.tail.append(line.rstrip())

    def failure(self) -> str:
        if self.reader:
            self.reader.join(timeout=1)
        detail = "\n".join(self.tail)
        return f"{self.name} 已退出（退出码 {self.process.returncode}）。\n{detail}\n日志：{self.log_path}"


class Launcher:
    def __init__(self, port: int, env: dict[str, str]):
        self.port = port
        self.env = env
        self.services: list[Service] = []
        self.job = ProcessJob()
        self.log_dir = PROJECT_ROOT / "data/logs/launcher" / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.url = f"http://127.0.0.1:{port}"

    def start(self, name: str, command: list[str], cwd: Path) -> Service:
        print(f"正在启动 {name}…", flush=True)
        process = subprocess.Popen(
            command, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            self.job.assign(process)
        except Exception:
            process.terminate()
            process.wait(timeout=5)
            raise
        service = Service(name, process, self.log_dir / f"{name}.log")
        service.reader = threading.Thread(target=service.collect, daemon=True)
        self.services.append(service)
        service.reader.start()
        return service

    def check_processes(self):
        for service in self.services:
            if service.process.poll() is not None:
                raise StartupError(service.failure())

    def wait_ready(self, name: str, url: str, *, worker_pid: int | None = None, timeout: float = 60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_processes()
            try:
                with HTTP.open(url, timeout=1) as response:
                    if response.status == 200:
                        if worker_pid is not None:
                            body = json.loads(response.read())
                            worker = body.get("checks", {}).get("worker", {})
                            if f":{worker_pid}:" not in (worker.get("instance_id") or ""):
                                raise StartupError("健康检查返回的是其他 worker，已停止本次启动")
                        print(f"{name} 已就绪。", flush=True)
                        return
            except (HTTPError, URLError, TimeoutError, OSError):
                pass
            time.sleep(0.25)
        raise StartupError(f"{name} 等待就绪超时。日志目录：{self.log_dir}")

    def write_state(self, status: str, error: str | None = None):
        state = {"status": status, "url": self.url, "launcher_pid": os.getpid(), "log_dir": str(self.log_dir),
                 "services": [{"name": service.name, "pid": service.process.pid} for service in self.services], "error": error}
        (PROJECT_ROOT / "data/launcher.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def wait_previous_worker(self):
        # Closing a console kills its job immediately; the former lease can live another 30s.
        try:
            response = HTTP.open("http://127.0.0.1:8000/health/pipeline", timeout=2)
        except HTTPError as response_error:
            response = response_error
        with response:
            worker = json.loads(response.read()).get("checks", {}).get("worker", {})
        expiry = worker.get("lease_expires_at")
        if not expiry:
            return
        expires_at = datetime.fromisoformat(expiry).replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return
        if existing_workers():
            raise StartupError("其他 worker 已在运行，已停止本次启动")
        print("等待上次后台任务的运行租约到期（最多约 30 秒）…", flush=True)
        deadline = time.monotonic() + 35
        while datetime.now(timezone.utc) <= expires_at:
            self.check_processes()
            if time.monotonic() >= deadline:
                raise StartupError("上次后台任务的租约尚未到期，请稍后重试")
            time.sleep(0.25)

    def run(self, frontend_only: bool, no_browser: bool):
        self.write_state("starting")
        if not frontend_only:
            self.start("后端", [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-proxy-headers", "--no-access-log"], PROJECT_ROOT)
            self.wait_ready("后端", "http://127.0.0.1:8000/health/ready")
            self.wait_previous_worker()
            worker = self.start("后台任务", [sys.executable, "-m", "backend.worker"], PROJECT_ROOT)
            self.wait_ready("后台任务", "http://127.0.0.1:8000/health/pipeline", worker_pid=worker.process.pid)
        self.start("网页", [shutil.which("node"), str(PROJECT_ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(self.port), "--strictPort"], PROJECT_ROOT / "frontend")
        self.wait_ready("网页", self.url + "/")
        self.write_state("ready")
        print(f"\nGlean 已启动：{self.url}/\n服务日志：{self.log_dir}\n在此窗口按 Ctrl+C 停止本次启动的所有服务；直接关闭窗口也会收回它们。", flush=True)
        if not no_browser:
            webbrowser.open(self.url + "/")
        while True:
            self.check_processes()
            time.sleep(0.5)

    def close(self):
        # All handles belong to services started here; pre-existing processes are untouched.
        original_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            signaled = False
            for service in reversed(self.services):
                if service.process.poll() is None:
                    try:
                        service.process.send_signal(signal.CTRL_BREAK_EVENT)
                        signaled = True
                    except OSError:
                        pass
            deadline = time.monotonic() + (8 if signaled else 0)
            while any(service.process.poll() is None for service in self.services) and time.monotonic() < deadline:
                time.sleep(0.1)
            self.job.close()
            for service in self.services:
                service.process.wait(timeout=5)
                if service.reader:
                    service.reader.join(timeout=2)
                service.process.stdout.close()
        finally:
            self.job.close()
            signal.signal(signal.SIGINT, original_handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    args = parser.parse_args()
    launcher = None
    status = "stopped"
    error_text = None
    exit_code = 0
    try:
        port, env = prepare(args.frontend_only)
        if args.check_only:
            print(f"启动检查通过：依赖正常，网页端口 {port} 可监听" + ("，后端端口 8000 可监听，没有重复 worker。" if not args.frontend_only else "。"), flush=True)
            return 0
        launcher = Launcher(port, env)
        launcher.run(args.frontend_only, args.no_browser)
    except KeyboardInterrupt:
        print("\n正在停止 Glean…", flush=True)
    except Exception as error:
        status = "failed"
        error_text = str(error)
        exit_code = 1
        print(f"\n启动或运行失败：{error_text}", file=sys.stderr, flush=True)
    finally:
        if launcher:
            launcher.close()
            launcher.write_state(status, error_text)
            print("本次启动的服务已停止。", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
