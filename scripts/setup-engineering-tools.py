#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/setup-engineering-tools.py
# Purpose: Create a repeatable local environment for the Engineering Toolkit.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Added repeatable setup and recorded-environment verification.
# Full history: docs/CHANGELOG.md and Git history.

"""Create or refresh an isolated VirtualGlove Engineering Toolkit environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PINNED_DEPENDENCIES = {
    "engineering-analysis": {
        "av": "16.1.0",
        "numpy": "1.26.4",
        "opencv-python-headless": "4.11.0.86",
        "Pillow": "12.3.0",
    },
    "engineering": {
        "av": "16.1.0",
        "mediapipe": "0.10.35",
        "numpy": "1.26.4",
        "opencv-python-headless": "4.11.0.86",
        "Pillow": "12.3.0",
    },
}


def environment_python(environment: Path) -> Path:
    """Return the virtual-environment interpreter for the current platform."""
    directory = "Scripts" if sys.platform == "win32" else "bin"
    executable = "python.exe" if sys.platform == "win32" else "python"
    return environment / directory / executable


def require_supported_python(version: tuple[int, int], with_mediapipe: bool) -> None:
    """Reject interpreters outside the toolkit's tested compatibility range."""
    if version < (3, 10):
        raise SystemExit("VirtualGlove Engineering Tools require Python 3.10 or newer")
    if with_mediapipe and version != (3, 12):
        raise SystemExit(
            "MediaPipe experiments use the validated Python 3.12 toolchain. "
            "Run this script with python3.12, or omit --with-mediapipe."
        )


def run(command: list[str], environment: dict[str, str] | None = None) -> None:
    """Run one visible setup command and stop on the first failure."""
    subprocess.run(command, cwd=ROOT, check=True, env=environment)


def python_identity(python: Path) -> dict[str, object]:
    """Read the target environment identity using its own interpreter."""
    source = (
        "import json,platform,sys; print(json.dumps({"
        "'version':list(sys.version_info[:3]),'platform':platform.platform()}))"
    )
    return json.loads(subprocess.check_output(
        [str(python), "-c", source], cwd=ROOT, text=True
    ))


def frozen_packages(python: Path) -> list[str]:
    """Return a path-free, normalized record of the installed environment."""
    frozen = subprocess.check_output(
        [str(python), "-m", "pip", "freeze", "--all"], cwd=ROOT, text=True,
        stderr=subprocess.DEVNULL,
    ).splitlines()
    return sorted((
        item for item in frozen
        if not item.startswith("-e ")
        and not item.casefold().startswith("virtualglove @ file:")
    ), key=str.casefold)


def toolkit_version() -> str:
    """Return the extracted package version or the local working-tree marker."""
    manifest_path = ROOT / "engineering-tools.json"
    if not manifest_path.is_file():
        return "working-tree"
    try:
        value = json.loads(manifest_path.read_text())["version"]
    except (KeyError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Engineering Toolkit manifest is invalid: {error}") from error
    if not isinstance(value, str) or not value:
        raise SystemExit("Engineering Toolkit manifest version is invalid")
    return value


def installed_versions(python: Path, names: list[str]) -> dict[str, str]:
    """Read direct dependency versions from the target environment."""
    source = (
        "import importlib.metadata,json,sys; "
        "print(json.dumps({name:importlib.metadata.version(name) for name in sys.argv[1:]}))"
    )
    try:
        return json.loads(subprocess.check_output(
            [str(python), "-c", source, *names], cwd=ROOT, text=True,
            stderr=subprocess.STDOUT,
        ))
    except subprocess.CalledProcessError as error:
        detail = error.output.strip().splitlines()
        raise SystemExit(
            "Engineering environment is missing a required package: "
            + (detail[-1] if detail else "unknown package")
        ) from error


def record_environment(python: Path, destination: Path, mode: str) -> None:
    """Record exact resolved packages without storing host credentials or paths."""
    identity = python_identity(python)
    record = {
        "format": 1,
        "mode": mode,
        "toolkit_version": toolkit_version(),
        "python": ".".join(str(part) for part in identity["version"]),
        "platform": identity["platform"],
        "packages": frozen_packages(python),
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    os.replace(temporary, destination)


def verify_environment(python: Path, destination: Path, mode: str) -> None:
    """Require the saved identity, resolved set, and pinned packages to match."""
    try:
        record = json.loads(destination.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(
            "Engineering environment record is missing or invalid; rerun setup without --check."
        ) from error
    identity = python_identity(python)
    expected_python = ".".join(str(part) for part in identity["version"])
    expected = {
        "format": 1,
        "mode": mode,
        "toolkit_version": toolkit_version(),
        "python": expected_python,
        "packages": frozen_packages(python),
    }
    for field in expected:
        if record.get(field) != expected[field]:
            raise SystemExit(
                f"Engineering environment {field} does not match its recorded setup; "
                "rerun setup without --check."
            )
    pins = PINNED_DEPENDENCIES[mode]
    actual = installed_versions(python, list(pins))
    mismatches = [
        f"{name} {actual.get(name, 'missing')} (expected {version})"
        for name, version in pins.items() if actual.get(name) != version
    ]
    if mismatches:
        raise SystemExit(
            "Engineering environment has unexpected direct dependencies: "
            + "; ".join(mismatches)
        )


def parser() -> argparse.ArgumentParser:
    """Build the supported environment-setup command line."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--environment", type=Path, default=ROOT / ".venv-engineering",
        help="environment directory (default: .venv-engineering)",
    )
    result.add_argument(
        "--with-mediapipe", action="store_true",
        help="also install the validated MediaPipe experiment dependency group",
    )
    result.add_argument(
        "--check", action="store_true",
        help="verify the existing environment without installing or changing it",
    )
    return result


def main() -> int:
    """Create, document, or verify the isolated toolkit environment."""
    args = parser().parse_args()
    python = environment_python(args.environment.resolve())
    extra = "engineering" if args.with_mediapipe else "engineering-analysis"
    if python.is_file():
        identity = python_identity(python)
        target_version = tuple(identity["version"][:2])
    else:
        target_version = sys.version_info[:2]
    require_supported_python(target_version, args.with_mediapipe)
    if not args.check:
        if not python.is_file():
            run([sys.executable, "-m", "venv", str(args.environment)])
        run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
        run([str(python), "-m", "pip", "install", "-e", f".[{extra}]"])
        record_environment(
            python, args.environment / "virtualglove-engineering-environment.json", extra
        )
    if not python.is_file():
        raise SystemExit(f"Engineering environment not found: {args.environment}")
    record = args.environment / "virtualglove-engineering-environment.json"
    if args.check:
        verify_environment(python, record, extra)
    imports = ["numpy", "cv2"] + (["mediapipe"] if args.with_mediapipe else [])
    saved_cache = args.environment.resolve() / ".matplotlib"
    if not args.check:
        saved_cache.mkdir(parents=True, exist_ok=True)
    cache_context = (
        tempfile.TemporaryDirectory(prefix="virtualglove-engineering-check-")
        if args.check or not saved_cache.is_dir()
        else None
    )
    cache = saved_cache if cache_context is None else Path(cache_context.name)
    try:
        check_environment = dict(os.environ)
        check_environment["MPLCONFIGDIR"] = str(cache)
        check_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        run(
            [str(python), "-c", ";".join(f"import {name}" for name in imports)],
            check_environment,
        )
    finally:
        if cache_context is not None:
            cache_context.cleanup()
    run([str(python), "scripts/check-engineering-toolkit.py"])
    print(f"VirtualGlove Engineering Toolkit is ready: {python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
