from __future__ import annotations

import os
import sys


def _bootstrap_environment(argv: list[str]) -> None:
    try:
        index = argv.index("--env")
    except ValueError:
        return
    if index + 1 < len(argv):
        os.environ["AINEWS_ENV"] = argv[index + 1]


def main() -> int:
    _bootstrap_environment(sys.argv[1:])
    from .app import main as run

    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
