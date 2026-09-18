#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/run-tests.py
# Purpose: Run tests through one dependency-complete local environment.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-18 - Added dependency-complete local test environment preflight.
# Full history: docs/CHANGELOG.md and Git history.

"""Create or reuse the supported local test environment, then run unittest."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENVIRONMENT = ROOT / ".venv-test"
DEPENDENCIES = (
    "numpy==1.26.4",
    "opencv-python-headless==4.11.0.86",
)


def environment_python(environment: Path) -> Path:
    """Return the virtual-environment interpreter for this platform."""
    if sys.platform == "win32":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def setup_python() -> str:
    """Choose Python 3.12 for the pinned local test dependency set."""
    if sys.version_info[:2] == (3, 12):
        return sys.executable
    candidate = shutil.which("python3.12")
    if candidate:
        return candidate
    raise SystemExit(
        "VirtualGlove test setup requires Python 3.12. Install it, then rerun "
        "python3 scripts/run-tests.py --setup."
    )


def setup(environment: Path) -> None:
    """Create the test environment and install its two pinned dependencies."""
    python = environment_python(environment)
    if not python.is_file():
        subprocess.run(
            [setup_python(), "-m", "venv", str(environment)],
            cwd=ROOT,
            check=True,
        )
    subprocess.run(
        [
            str(python), "-m", "pip", "install", "--disable-pip-version-check",
            "--editable", ".[test]",
        ],
        cwd=ROOT,
        check=True,
    )


def dependencies_ready(python: Path) -> bool:
    """Check exact direct dependencies without printing import tracebacks."""
    check = (
        "import cv2,numpy;"
        "assert numpy.__version__=='1.26.4';"
        "assert cv2.__version__=='4.11.0'"
    )
    return subprocess.run(
        [str(python), "-c", check],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def parser() -> argparse.ArgumentParser:
    """Build the bounded local test-runner command line."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--environment", type=Path, default=DEFAULT_ENVIRONMENT,
        help="test virtual environment (default: .venv-test)",
    )
    result.add_argument(
        "--setup", action="store_true",
        help="create or repair the pinned test environment before running",
    )
    result.add_argument("--quiet", action="store_true", help="use compact unittest output")
    result.add_argument("tests", nargs="*", help="optional unittest module or test names")
    return result


def main() -> int:
    """Refuse incomplete environments before test discovery can emit noise."""
    args = parser().parse_args()
    environment = args.environment.resolve()
    python = environment_python(environment)
    if args.setup:
        setup(environment)
    if not python.is_file() or not dependencies_ready(python):
        print(
            "VirtualGlove test environment is not ready. Run: "
            "python3 scripts/run-tests.py --setup",
            file=sys.stderr,
        )
        return 2
    command = [str(python), "-m", "unittest"]
    if args.tests:
        command.extend(args.tests)
        command.append("-q" if args.quiet else "-v")
    else:
        command.extend(("discover", "-s", "tests", "-q" if args.quiet else "-v"))
    environment_variables = dict(os.environ)
    environment_variables["PYTHONPATH"] = str(ROOT / "src")
    environment_variables["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(command, cwd=ROOT, env=environment_variables).returncode


if __name__ == "__main__":
    raise SystemExit(main())
