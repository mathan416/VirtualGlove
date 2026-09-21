#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-enclosure-packages.py
# Purpose: Build deterministic, design-specific enclosure print bundles.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-20 - Added deterministic per-design enclosure bundles.
# Full history: docs/CHANGELOG.md and Git history.
"""Build and verify the public enclosure print-file archives."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENCLOSURES = ROOT / "hardware/enclosures"
MANIFEST = ENCLOSURES / "enclosure-files.json"
OUTPUT = ENCLOSURES / "bundles"
ZIP_TIME = (2026, 9, 20, 0, 0, 0)


def archive_name(group: str, relative: str) -> str:
    """Place one existing source file in its plain-language bundle folder."""
    return f"{group}/{Path(relative).name}"


def add_bytes(package: zipfile.ZipFile, name: str, body: bytes) -> None:
    """Write one deterministic archive member."""
    item = zipfile.ZipInfo(name, ZIP_TIME)
    item.compress_type = zipfile.ZIP_DEFLATED
    item.external_attr = 0o644 << 16
    package.writestr(item, body)


def parts_text(title: str, structural: list[str], branding: list[str],
               fit_tests: list[str]) -> str:
    """Explain required, alternative, and optional files without ambiguity."""
    lines = [
        f"{title} - VirtualGlove print files", "",
        "STRUCTURAL PARTS", "Print the base and exactly one lid:",
        *[f"- {Path(name).name}" for name in structural], "",
        "FINISHING", "- virtualglove-matrix-bezel.stl is optional but recommended.", "",
        "BRANDING", "Choose one complete logo set matching the selected lid:",
        *[f"- {Path(name).name}" for name in branding], "",
        "FIT TESTS", "Print these before the structural parts:",
        *[f"- {Path(name).name}" for name in fit_tests], "",
        "The large target-badge files are optional decorations and are deliberately",
        "not included: they do not fit any lid recess.", "",
        "Use the VirtualGlove Enclosure Guide and Assembly Quick Reference before printing.",
    ]
    return "\n".join(lines) + "\n"


def build() -> list[Path]:
    """Build every archive declared by the checked enclosure manifest."""
    data = json.loads(MANIFEST.read_text())
    if data.get("version") != 1:
        raise ValueError("Unsupported enclosure manifest version")
    shared = data["shared"]
    branding_groups = data["branding"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    expected = set()
    built = []
    for design in data["designs"].values():
        output = OUTPUT / design["archive"]
        expected.add(output.name)
        structural = list(design["structural"])
        fit_tests = [shared[key] for key in design["fit_tests"]]
        branding = [name for key in design["branding"] for name in branding_groups[key]]
        files = structural + [shared["matrix_bezel"]] + fit_tests + branding + [shared["source"]]
        if len(files) != len(set(files)):
            raise ValueError(f"Duplicate file in {design['title']} bundle")
        for relative in files:
            if not (ENCLOSURES / relative).is_file():
                raise ValueError(f"Missing enclosure source: {relative}")
        with zipfile.ZipFile(output, "w") as package:
            add_bytes(package, "PARTS.txt", parts_text(
                design["title"], structural, branding, fit_tests,
            ).encode())
            for relative in structural:
                add_bytes(package, archive_name("structural", relative),
                          (ENCLOSURES / relative).read_bytes())
            add_bytes(package, archive_name("finishing", shared["matrix_bezel"]),
                      (ENCLOSURES / shared["matrix_bezel"]).read_bytes())
            for relative in fit_tests:
                add_bytes(package, archive_name("fit-tests", relative),
                          (ENCLOSURES / relative).read_bytes())
            for relative in branding:
                add_bytes(package, archive_name("branding", relative),
                          (ENCLOSURES / relative).read_bytes())
            add_bytes(package, archive_name("source", shared["source"]),
                      (ENCLOSURES / shared["source"]).read_bytes())
        built.append(output)
    for stale in OUTPUT.glob("*.zip"):
        if stale.name not in expected:
            stale.unlink()
    return built


def main() -> int:
    """Build archives and print their stable paths."""
    for path in build():
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
