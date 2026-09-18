# Project: VirtualGlove
# File: src/virtualglove/versioning.py
# Purpose: Identify the release version and source branch in checkouts and deployed builds.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Identify exact software builds and expected matrix firmware source.
#   2026-09-04 - Derive the displayed version from release and build metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Release and build identity without requiring Git on the deployed accessory."""

import json
import hashlib
import os
import re
import subprocess
from pathlib import Path


def firmware_source_id(root):
    """Fingerprint the sketch and its pinned build profile, excluding its generated stamp."""
    digest = hashlib.sha256()
    paths = sorted(p for p in (root / "sketch").rglob("*")
                   if p.is_file() and p.name != "firmware_version.h" and
                   p.suffix in (".ino", ".h", ".cpp", ".c", ".yaml"))
    if not paths:
        return None
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def exact_build_identity(root):
    """Add immutable source identity while retaining the existing version label contract."""
    identity = build_identity(root)
    def git(*args):
        """Read one bounded Git value without exposing command errors to the UI."""
        try:
            return subprocess.check_output(["git", *args], cwd=str(root), stderr=subprocess.DEVNULL,
                                           universal_newlines=True, timeout=5).strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    commit = git("rev-parse", "HEAD")
    identity["commit"] = commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None
    identity["release"] = os.environ.get("RELEASE_VERSION") or git("describe", "--tags", "--exact-match", "HEAD") or None
    identity["dirty"] = bool(git("status", "--porcelain", "--", "src", "python", "scripts", "sketch", "bricks", "config", "app.yaml", "pyproject.toml"))
    identity["firmware_expected"] = firmware_source_id(root)
    return identity


def current_identity():
    """Read exact exported metadata; older packages report unavailable fields honestly."""
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists():
        return exact_build_identity(root)
    stamp = Path(__file__).with_name("_build_info.json")
    try:
        result = json.loads(stamp.read_text())
        manifest = root / "install-release.json"
        if manifest.is_file():
            result["release"] = json.loads(manifest.read_text())["version"]
        return result
    except (OSError, ValueError, KeyError):
        return {"version": current_version(), "branch": "unknown", "commit": None,
                "release": None, "firmware_expected": firmware_source_id(root)}


def build_identity(root):
    """Read the authoritative release number and detect the source branch."""
    text = (root / "pyproject.toml").read_text()
    project = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", text).group(1)
    version = re.search(r'^version\s*=\s*"([^"]+)"', project, re.M).group(1)
    branch = "unknown"
    if (root / ".git").exists():
        try:
            branch = subprocess.check_output(
                ["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=str(root),
                stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or "unknown"
    return {"version": version, "branch": branch}


def display_version(identity):
    """Mark dev builds while keeping main release numbers unchanged."""
    return identity["version"] + ("-dev" if identity["branch"] == "dev" else "")


def current_version():
    """Prefer live checkout identity, otherwise read the packaged build stamp."""
    root = Path(__file__).resolve().parents[2]
    stamp = Path(__file__).with_name("_build_info.json")
    if (root / ".git").exists():
        return display_version(build_identity(root))
    if stamp.is_file():
        return display_version(json.loads(stamp.read_text()))
    if (root / "pyproject.toml").is_file():
        return display_version(build_identity(root))
    try:
        from importlib.metadata import version
        return version("virtualglove")
    except (ImportError, LookupError):
        return "unknown"
