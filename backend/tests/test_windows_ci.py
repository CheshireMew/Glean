from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name == "nt", "Windows CI uses PowerShell")
class WindowsCIExitTest(unittest.TestCase):
    def test_each_required_command_failure_reaches_the_step_exit(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        blocks = re.findall(r"        run: \|\n((?:          [^\n]*\n)+)", workflow)
        self.assertEqual(len(blocks), 2)
        pwsh = shutil.which("pwsh")
        self.assertIsNotNone(pwsh, "The Windows validation runner requires pwsh")
        sentinel = sys.executable.replace("'", "''")
        for block in blocks:
            lines = [line[10:] for line in block.splitlines()]
            commands = [i for i, line in enumerate(lines) if line.startswith(("python ", "npm "))]
            self.assertIn(len(commands), (3, 5))
            for failed_command in commands:
                with self.subTest(command=lines[failed_command]):
                    injected = list(lines)
                    for index in commands:
                        code = 7 if index == failed_command else 0
                        injected[index] = f"& '{sentinel}' -c 'import sys; sys.exit({code})'"
                    # The GitHub runner's final exit check cannot rescue an earlier masked failure.
                    injected.append("if (Test-Path variable:LASTEXITCODE) { exit $LASTEXITCODE }")
                    completed = subprocess.run(
                        [pwsh, "-NoProfile", "-NonInteractive", "-Command", "\n".join(injected)],
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(completed.returncode, 7, completed.stderr)
