#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/check-source-docs.py
# Purpose: Enforce standard source headers and production Python interface documentation.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Audit new nonignored source files before their first commit.
#   2026-09-03 - Added the repository source-documentation audit.
#   2026-09-03 - Added the GitHub Actions workflow to audited configuration.
#   2026-09-04 - Preserved upstream headers in accepted third-party source trees.
# Full history: docs/CHANGELOG.md and Git history.

"""Audit tracked source files for required headers and useful Python docstrings."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HEADER_MARKERS = (
    "Project: VirtualGlove",
    "File:",
    "Purpose:",
    "Author: Iain Bennett",
    "Copyright (c) 2026 Iain Bennett",
    "SPDX-License-Identifier: MIT",
    "Change log:",
    "Full history: docs/CHANGELOG.md and Git history.",
)
SOURCE_SUFFIXES = {".py", ".sh", ".ino", ".service", ".timer", ".path", ".cfg"}
COMMENTED_CONFIGS = {
    ".github/workflows/quality.yml",
    ".github/workflows/install-release.yml",
    "app.yaml",
    "sketch/sketch.yaml",
    "pyproject.toml",
}
UNDOCUMENTED_FRAMEWORK_METHODS = {"__init__", "do_GET", "do_POST", "log_message"}
THIRD_PARTY_PREFIXES = ("third_party/", "vendor/")


def tracked_source_files() -> list[Path]:
    """Return present tracked and new source/configuration files."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    files = []
    for name in output:
        if not name:
            continue
        path = Path(name)
        if (
            (ROOT / path).is_file()
            and (path.suffix in SOURCE_SUFFIXES
                 or name in COMMENTED_CONFIGS
                 or name.startswith("retropie/bin/"))
        ):
            files.append(path)
    return sorted(files)


def header_errors(path: Path) -> list[str]:
    """Return required header markers absent from a source file's opening block."""
    if str(path).startswith(THIRD_PARTY_PREFIXES):
        return []
    opening = "\n".join((ROOT / path).read_text().splitlines()[:20])
    return [marker for marker in HEADER_MARKERS if marker not in opening]


def python_documentation_errors(path: Path) -> list[str]:
    """Return missing module or production interface docstrings for one Python file."""
    if str(path).startswith(THIRD_PARTY_PREFIXES):
        return []
    tree = ast.parse((ROOT / path).read_text(), filename=str(path))
    errors = []
    if ast.get_docstring(tree) is None:
        errors.append("module docstring")
    if path.parts[0] == "tests":
        return errors

    class Visitor(ast.NodeVisitor):
        """Track qualified names while checking nested production interfaces."""

        def __init__(self) -> None:
            self.names: list[str] = []

        def _visit_documented(self, node: ast.AST) -> None:
            """Check one named node, then recurse while preserving its qualified name."""
            name = getattr(node, "name")
            qualified = ".".join([*self.names, name])
            if (
                name not in UNDOCUMENTED_FRAMEWORK_METHODS
                and ast.get_docstring(node) is None
            ):
                errors.append(qualified)
            self.names.append(name)
            self.generic_visit(node)
            self.names.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """Check a class and recursively inspect its methods and nested types."""
            self._visit_documented(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Check a synchronous function and recursively inspect nested helpers."""
            self._visit_documented(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Check an asynchronous function and recursively inspect nested helpers."""
            self._visit_documented(node)

    Visitor().visit(tree)
    return errors


def main() -> int:
    """Print actionable documentation failures and return a CI-friendly status."""
    failures = []
    files = tracked_source_files()
    for path in files:
        missing = header_errors(path)
        if missing:
            failures.append(f"{path}: missing header markers: {', '.join(missing)}")
        if path.suffix == ".py":
            undocumented = python_documentation_errors(path)
            if undocumented:
                failures.append(
                    f"{path}: missing docstrings: {', '.join(undocumented)}"
                )
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Source documentation audit passed for {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
