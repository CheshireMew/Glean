from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch
import uuid


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts/windows'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('glean_launcher_log_test', SCRIPTS / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)
sys.path.remove(str(SCRIPTS))


@unittest.skipUnless(os.name == 'nt', 'Windows launcher logs')
class LauncherLogTest(unittest.TestCase):
    def setUp(self):
        # Retain owned evidence; this test never removes files or directories.
        self.root = Path(os.environ.get('GLEAN_TEST_EVIDENCE_ROOT', r'D:\Tools\CodexAudits\Glean\launcher-log-tests')) / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        print(f'Launcher log evidence: {self.root}', flush=True)

    def test_actual_service_collector_bounds_output_and_keeps_failure_tail(self):
        command = "import sys; [print('long output ' * 1000) for _ in range(80)]; print('specific final failure'); sys.exit(7)"
        process = subprocess.Popen([sys.executable, '-c', command], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        self.addCleanup(process.stdout.close)
        service = launcher.Service('controlled', process, self.root / 'controlled.log')
        service.log_max_bytes = 2048
        service.run_id = 'controlled-run'
        service.collect()
        self.assertEqual(process.wait(timeout=5), 7)
        data = service.log_path.read_bytes()
        self.assertLessEqual(len(data), 2048)
        self.assertIn(b'specific final failure', data)
        self.assertIn(b'controlled-run', data)
        self.assertIn('specific final failure', service.failure())

    def test_repeated_launcher_starts_stop_before_exceeding_history_budget(self):
        env = {**os.environ, 'GLEAN_LAUNCHER_LOG_MAX_RUNS': '2', 'GLEAN_LAUNCHER_LOG_MAX_BYTES': '2048',
               'GLEAN_LAUNCHER_LOG_TOTAL_BYTES': '32768', 'GLEAN_LAUNCHER_LOG_RETENTION_DAYS': '14'}
        with patch.object(launcher, 'PROJECT_ROOT', self.root):
            for _ in range(2):
                manager = launcher.Launcher(5174, env)
                manager.close()
                manager.write_state('stopped')
            before = {path.relative_to(self.root) for path in self.root.rglob('*')}
            with self.assertRaisesRegex(Exception, '日志保留预算'):
                launcher.Launcher(5174, env)
            after = {path.relative_to(self.root) for path in self.root.rglob('*')}
        self.assertEqual(before, after)
        self.assertEqual(len(list((self.root / 'data/logs/launcher').iterdir())), 2)
        report = launcher.LogRunStore(self.root / 'data/logs/launcher', launcher.LogPolicy()).inspect()
        # Independently exercise total bytes and elapsed retention, so a run-count
        # limit cannot accidentally hide either admission boundary.
        byte_env = {**env, 'GLEAN_LAUNCHER_LOG_MAX_RUNS':'20',
                    'GLEAN_LAUNCHER_LOG_TOTAL_BYTES':str(report['bytes'] + 3 * 2048 + 4096 - 1)}
        with patch.object(launcher, 'PROJECT_ROOT', self.root):
            with self.assertRaisesRegex(Exception, '日志保留预算'):
                launcher.Launcher(5174, byte_env)
        manifest_path = Path(report['runs'][0]['path']) / 'run.json'
        import json
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['finished_at'] = '2000-01-01T00:00:00+00:00'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        age_env = {**env, 'GLEAN_LAUNCHER_LOG_MAX_RUNS':'20'}
        with patch.object(launcher, 'PROJECT_ROOT', self.root):
            with self.assertRaisesRegex(Exception, '日志保留预算'):
                launcher.Launcher(5174, age_env)
        self.assertEqual(before, {path.relative_to(self.root) for path in self.root.rglob('*')})
