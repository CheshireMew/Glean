from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts/windows"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("glean_windows_launcher", SCRIPTS / "launcher.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)
sys.path.remove(str(SCRIPTS))


@unittest.skipUnless(os.name == "nt", "Windows launcher")
class WindowsLauncherTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(launcher, "PROJECT_ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.directory.cleanup()

    def test_occupied_port_is_skipped_by_real_node_probe(self):
        with socket.socket() as busy:
            busy.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            occupied = busy.getsockname()[1]
            with socket.socket() as free:
                free.bind(("127.0.0.1", 0))
                available = free.getsockname()[1]
            port, unavailable = launcher.select_frontend_port([occupied, available])
            self.assertEqual(port, available)
            self.assertEqual(unavailable, [(occupied, "端口已占用或不可用")])

    def test_windows_access_denial_is_reported_and_skipped(self):
        reply = subprocess.CompletedProcess([], 0, json.dumps([
            {"port": 5173, "error": "EACCES"}, {"port": 5174, "ok": True},
        ]), "")
        with patch.object(launcher.subprocess, "run", return_value=reply):
            self.assertEqual(launcher.select_frontend_port(), (5174, [(5173, "Windows 拒绝访问")]))

    def test_early_child_failure_is_reported_without_waiting_for_timeout(self):
        manager = launcher.Launcher(5174, os.environ.copy())
        try:
            service = manager.start("failed", [sys.executable, "-c", "import time; print('specific startup failure', flush=True); time.sleep(0.2); raise SystemExit(7)"], self.root)
            service.process.wait(timeout=5)
            started = time.monotonic()
            with self.assertRaisesRegex(launcher.StartupError, "specific startup failure"):
                manager.wait_ready("failed", "http://127.0.0.1:1/", timeout=30)
            self.assertLess(time.monotonic() - started, 3)
        finally:
            manager.close()

    def test_cleanup_reclaims_started_service_and_its_descendant(self):
        manager = launcher.Launcher(5174, os.environ.copy())
        pid_file = self.root / "descendant.pid"
        code = (
            "import subprocess,sys,time; from pathlib import Path; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep(120)"
        )
        service = manager.start("tree", [sys.executable, "-c", code], self.root)
        try:
            deadline = time.monotonic() + 5
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(pid_file.exists())
            child_pid = int(pid_file.read_text())
        finally:
            manager.close()
        self.assertIsNotNone(service.process.poll())
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"[bool](Get-Process -Id {child_pid} -ErrorAction SilentlyContinue)"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.stdout.strip(), "False")

    def test_owner_termination_reclaims_child_without_running_cleanup(self):
        pid_file = self.root / "owned.pid"
        code = (
            "import os,subprocess,sys; from pathlib import Path; "
            f"sys.path.insert(0,{str(SCRIPTS)!r}); from process_job import ProcessJob; "
            "job=ProcessJob(); child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
            "job.assign(child); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid)); os._exit(0)"
        )
        owner = subprocess.Popen([sys.executable, "-c", code], creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(owner.wait(timeout=5), 0)
        self.assertTrue(pid_file.exists())
        child_pid = int(pid_file.read_text())
        deadline = time.monotonic() + 5
        while True:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", f"[bool](Get-Process -Id {child_pid} -ErrorAction SilentlyContinue)"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.stdout.strip() == "False" or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        self.assertEqual(result.stdout.strip(), "False")
