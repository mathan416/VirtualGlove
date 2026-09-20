#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/check-engineering-toolkit.py
# Purpose: Verify a cleanly extracted Engineering Toolkit without camera access.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Added package completeness, syntax, and safe command-help checks.
# Full history: docs/CHANGELOG.md and Git history.

"""Check that every packaged engineering command is present and can show help."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "engineering-tools.json"


def load_manifest() -> dict:
    """Load and minimally validate the generated toolkit manifest."""
    if not MANIFEST.is_file():
        inventory = runpy.run_path(str(ROOT / "scripts" / "package-inventory.py"))
        categories = inventory["TOOLKIT_CATEGORIES"]
        files = sorted({name for names in categories.values() for name in names})
        files.extend(["docs/ENGINEERING_TOOLKIT.md", "pyproject.toml"])
        return {
            "format": 2,
            "categories": categories,
            "tool_files": sorted({name for names in categories.values() for name in names}),
            "files": sorted(set(files)),
        }
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {MANIFEST.name}: {error}") from error
    if manifest.get("format") != 2 or not isinstance(manifest.get("categories"), dict):
        raise ValueError("unsupported or incomplete Engineering Toolkit manifest")
    return manifest


def validate_inventory(manifest: dict) -> None:
    """Require one category per tool and a complete, internally consistent file list."""
    categorized = []
    for category, names in manifest["categories"].items():
        if not isinstance(category, str) or not category or not isinstance(names, (list, tuple)):
            raise ValueError("malformed Engineering Toolkit category")
        if not all(isinstance(name, str) and name for name in names):
            raise ValueError(f"malformed tool path in category: {category}")
        categorized.extend(names)
    duplicates = sorted({name for name in categorized if categorized.count(name) > 1})
    if duplicates:
        raise ValueError("tools appear in more than one category: " + ", ".join(duplicates))
    tool_files = manifest.get("tool_files")
    if not isinstance(tool_files, list) or set(tool_files) != set(categorized):
        raise ValueError("Engineering Toolkit tool inventory does not match its categories")
    files = manifest.get("files")
    if not isinstance(files, list) or not set(tool_files).issubset(files):
        raise ValueError("Engineering Toolkit file inventory omits a supported tool")


def validate_path(name: str) -> Path:
    """Resolve one manifest path while preventing traversal and symbolic links."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe toolkit path: {name}")
    resolved = ROOT / path
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"missing or unsupported toolkit file: {name}")
    return resolved


def python_syntax(path: Path) -> None:
    """Compile Python source in memory so the check creates no cache files."""
    compile(path.read_text(), str(path), "exec")


def command_help(path: Path) -> None:
    """Require a Python command to expose dependency-free command-line help."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(path), "--help"], cwd=ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    if result.returncode or "usage:" not in result.stdout.lower():
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError(
            f"{path.relative_to(ROOT)} cannot show help: "
            f"{detail[-1] if detail else 'no diagnostic'}"
        )


def shell_check(path: Path, *, help_check: bool) -> None:
    """Parse a shell command and require its help path to remain read-only."""
    bash = shutil.which("bash")
    if bash is None:
        return
    result = subprocess.run(
        [bash, "-n", str(path)], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError(
            f"{path.relative_to(ROOT)} has invalid shell syntax: "
            f"{detail[-1] if detail else 'no diagnostic'}"
        )
    if not help_check:
        return
    result = subprocess.run(
        [bash, str(path), "--help"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    if result.returncode or "usage:" not in result.stdout.lower():
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError(
            f"{path.relative_to(ROOT)} cannot show help safely: "
            f"{detail[-1] if detail else 'no diagnostic'}"
        )


def parser() -> argparse.ArgumentParser:
    """Build the package self-check command line."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--skip-help", action="store_true",
        help="check files and syntax without starting each command",
    )
    return result


def main() -> int:
    """Validate the manifest, packaged source, and supported command surfaces."""
    args = parser().parse_args()
    manifest = load_manifest()
    validate_inventory(manifest)
    commands = sorted({
        name for names in manifest["categories"].values() for name in names
        if name.endswith(".py") and name != "scripts/check-engineering-toolkit.py"
    })
    all_files = sorted(set(manifest.get("files", [])))
    shell_commands = []
    for name in all_files:
        path = validate_path(name)
        if path.suffix == ".py":
            python_syntax(path)
        elif path.suffix == ".sh":
            shell_check(path, help_check=not args.skip_help)
            shell_commands.append(name)
    if not args.skip_help:
        for name in commands:
            command_help(ROOT / name)
    print(
        f"Engineering Toolkit check passed: {len(all_files)} files, "
        f"{len(commands)} Python commands, {len(shell_commands)} shell commands."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
