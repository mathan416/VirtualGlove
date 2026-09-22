#!/usr/bin/env python3
# Project: VirtualGlove
# File: website/build.py
# Purpose: Render and validate the static public website from release facts.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-21 - Added the Engineering page to the tracked release website.
#   2026-09-20 - Added the tracked four-page release website build.
# Full history: docs/CHANGELOG.md and Git history.
"""Build a dependency-free, uploadable VirtualGlove website."""

from __future__ import annotations

import html
import json
import re
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "website/src"
DIST = ROOT / "website/dist"
OUTPUT = ROOT / "output/website/VirtualGlove-Website.zip"
ZIP_TIME = (2026, 9, 20, 0, 0, 0)


def command(value: str) -> str:
    """Escape a copyable command for literal HTML code content."""
    return html.escape(value, quote=False)


def values() -> dict[str, str]:
    """Derive every release-sensitive site value from the checked facts file."""
    facts = json.loads((ROOT / "config/release.json").read_text())
    version = facts["project_version"]
    tag = facts["release_tag"]
    stable = facts["channel"] == "stable"
    base = f"https://github.com/mathan416/VirtualGlove/releases/download/{tag}"
    return {
        "VERSION": version,
        "TAG": tag,
        "REF": tag,
        "RELEASE_LABEL": (f"Stable release · {tag}" if stable
                          else f"Release candidate · {tag}"),
        "RELEASE_NOTE": (
            f"VirtualGlove {version} is the current stable release. Install the "
            "same release on the Controller and console."
            if stable else
            f"Release candidates are for testing before the final {version} release. "
            "Install the same candidate on the Controller and console."
        ),
        "INSTALL_RELEASE_NOTE": (
            f"These commands are pinned to {tag} so the Controller and console use "
            "the same stable release."
            if stable else
            f"These commands are pinned to {tag} rather than the latest stable release."
        ),
        "RELEASE_URL": f"https://github.com/mathan416/VirtualGlove/releases/tag/{tag}",
        "DOC_ROOT": f"https://github.com/mathan416/VirtualGlove/blob/{tag}",
        "RAW_ROOT": f"https://github.com/mathan416/VirtualGlove/raw/{tag}",
        "UNO_COMMAND": command(
            "cd /home/arduino\n"
            f"curl -fLO {base}/install-uno-q.sh\n"
            f"bash install-uno-q.sh --version {tag}"
        ),
        "RETROPIE_COMMAND": command(
            "cd \"$HOME\"\n"
            f"curl -fLO {base}/install-retropie.sh\n"
            f"bash install-retropie.sh --version {tag}"
        ),
        "RECALBOX_COMMAND": command(
            "cd /recalbox/share/system\n"
            f"curl -fLO {base}/install-recalbox.sh\n"
            f"bash install-recalbox.sh --version {tag}"
        ),
        "BATOCERA_COMMAND": command(
            "cd /userdata/system\n"
            f"curl -fLO {base}/install-batocera.sh\n"
            f"bash install-batocera.sh --version {tag}"
        ),
        "LAUNCHBOX_COMMAND": command(
            "$destination = Join-Path $env:USERPROFILE \"Downloads\\VirtualGlove-LaunchBox\"\n"
            f"Invoke-WebRequest \"{base}/VirtualGlove-LaunchBox.zip\" -OutFile \"$destination.zip\"\n"
            "Expand-Archive \"$destination.zip\" -DestinationPath $destination -Force\n"
            "Set-Location \"$destination\\VirtualGlove\"\n"
            "powershell -ExecutionPolicy Bypass -File .\\launchbox\\install-launchbox.ps1 `\n"
            "  -LaunchBoxRoot \"D:\\LaunchBox\" `\n"
            "  -RetroArchRoot \"D:\\LaunchBox\\Emulators\\RetroArch\" `\n"
            "  -ControllerHost \"virtualglove.local\""
        ),
    }


def render(text: str, replacements: dict[str, str]) -> str:
    """Replace the bounded token vocabulary and reject unresolved placeholders."""
    for name, value in replacements.items():
        text = text.replace("@@" + name + "@@", value)
    unresolved = sorted(set(re.findall(r"@@[A-Z_]+@@", text)))
    if unresolved:
        raise ValueError("Unresolved website tokens: " + ", ".join(unresolved))
    return text


def validate() -> None:
    """Check internal pages, current behaviour, install steps, and release identity."""
    pages = {path.name for path in DIST.glob("*.html")}
    if pages != {"index.html", "install.html", "build.html", "about.html",
                 "engineering.html"}:
        raise ValueError("Website page set is incomplete")
    combined = "\n".join(path.read_text() for path in DIST.glob("*.html"))
    if re.search(r"Get ready to play|Ready-to-Play|/ready", combined, re.I):
        raise ValueError("Website advertises the retired Ready-to-Play feature")
    facts = json.loads((ROOT / "config/release.json").read_text())
    if facts["release_tag"] not in combined or "v0.4.1" in combined:
        raise ValueError("Website release identity is stale")
    prose = html.unescape(re.sub(r"<[^>]+>", " ", combined))
    american_spellings = re.compile(
        r"\b(?:behaviors?|colors?|colored|coloring|centers?|centered|centering|"
        r"labors?|labored|laboring|recognizes?|recognized|recognizing|"
        r"customizes?|customized|customizing)\b",
        re.IGNORECASE,
    )
    stale_spelling = american_spellings.search(prose)
    if stale_spelling:
        raise ValueError(
            "Website public prose uses American spelling: "
            + stale_spelling.group(0)
        )
    for step in ("cd /home/arduino", 'cd "$HOME"',
                 "cd /recalbox/share/system", "cd /userdata/system", "Set-Location"):
        if step not in (DIST / "install.html").read_text():
            raise ValueError("Website install instructions are missing: " + step)
    for path in DIST.glob("*.html"):
        text = path.read_text()
        for target in re.findall(r'(?:href|src|poster)="([^"]+)"', text):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            if local and not (DIST / local).is_file():
                raise ValueError(f"Broken website link in {path.name}: {target}")
    for source in SOURCE.glob("*.html"):
        for linked_path in re.findall(r'@@DOC_ROOT@@/([^"#]+)', source.read_text()):
            if not (ROOT / linked_path).is_file():
                raise ValueError(
                    f"Missing project guide linked from {source.name}: {linked_path}"
                )


def build() -> Path:
    """Render the source tree and create a deterministic manual-upload ZIP."""
    replacements = values()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(
        SOURCE / "assets", DIST / "assets",
        ignore=shutil.ignore_patterns(".DS_Store"),
    )
    for source in SOURCE.glob("*.html"):
        (DIST / source.name).write_text(render(source.read_text(), replacements))
    validate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(DIST.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                item = zipfile.ZipInfo(path.relative_to(DIST).as_posix(), ZIP_TIME)
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o644 << 16
                package.writestr(item, path.read_bytes())
    with zipfile.ZipFile(OUTPUT) as package:
        archived = {name: package.read(name) for name in package.namelist()}
    expected = {
        path.relative_to(DIST).as_posix(): path.read_bytes()
        for path in DIST.rglob("*")
        if path.is_file() and path.name != ".DS_Store"
    }
    if archived != expected:
        raise ValueError("Website upload ZIP does not exactly match website/dist")
    return OUTPUT


if __name__ == "__main__":
    result = build()
    print(result.relative_to(ROOT))
