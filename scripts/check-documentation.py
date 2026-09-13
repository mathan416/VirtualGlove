#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/check-documentation.py
# Purpose: Validate project documentation layout, local links, configuration coverage, and PDF editions.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Registered the Engineering Toolkit manual and PDF.
#   2026-09-10 - Consolidated Programs into Gameplay and registered the Engineering Journey.
#   2026-09-05 - Kept Pixel Pal's Extra-Digit Hunt counts synchronized with guide art.
#   2026-09-04 - Guarded the Nestopia revision and patch digest in third-party records.
#   2026-09-04 - Limited Help coverage checks to guides directly under docs.
#   2026-09-03 - Added documentation and generated-PDF consistency checks.
#   2026-09-03 - Registered the illustrated gameplay handbook and PDF edition.
#   2026-09-03 - Added Help-library and registered-game coverage checks.
#   2026-09-03 - Allowed the Gun Smoke display title for its punctuated ROM basename.
# Full history: docs/CHANGELOG.md and Git history.

"""Check that maintained documentation is complete, linked, and publishable."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
HELP_FILE = re.compile(r'[\"\x27]file[\"\x27]\s*:\s*[\"\x27]([^\"\x27]+\.md)[\"\x27]')
CONFIGURATION_FILES = (
    "config/device.example.json",
    "config/games.json",
    "config/launcher.example.json",
    "config/profiles.json",
    "app.yaml",
    "sketch/sketch.yaml",
    "pyproject.toml",
    "retropie/retroarch/VirtualGlove.cfg",
    "retropie/virtualglove-receiver.service",
    "retropie/virtualglove-receiver.timer",
    "retropie/virtualglove-games.service",
    "uno-q/virtualglove-system-shutdown.path",
    "uno-q/virtualglove-system-shutdown.service",
    "uno-q/virtualglove-system-shutdown.conf",
    ".github/workflows/quality.yml",
)
PDF_EDITIONS = {
    "THIRD_PARTY_NOTICES.md": "VirtualGlove-Third-Party-Notices.pdf",
    "docs/BUILD_YOUR_OWN.md": "VirtualGlove-Build-Your-Own.pdf",
    "docs/NATIVE_EMULATION_EXPLAINED.md": "VirtualGlove-Native-Emulation.pdf",
    "docs/TROUBLESHOOTING.md": "VirtualGlove-Troubleshooting.pdf",
    "docs/CAMERA_GUIDE.md": "VirtualGlove-Camera-Guide.pdf",
    "docs/ENGINEERING_JOURNEY.md": "VirtualGlove-Engineering-Journey.pdf",
    "docs/ENGINEERING_TOOLKIT.md": "VirtualGlove-Engineering-Toolkit.pdf",

    "docs/MATRIX_GUIDE.md": "VirtualGlove-Matrix-Guide.pdf",
    "docs/ARCHITECTURE.md": "VirtualGlove-Architecture.pdf",
    "README.md": "VirtualGlove-Overview.pdf",
    "docs/INSTALL_README.md": "VirtualGlove-Guide.pdf",
    "docs/cheatsheet.md": "VirtualGlove-Quick-Reference.pdf",
    "docs/CHANGELOG.md": "VirtualGlove-Changelog.pdf",
    "docs/CONFIGURATION_REFERENCE.md": "VirtualGlove-Configuration-Reference.pdf",
    "docs/SECURITY.md": "VirtualGlove-Security.pdf",
    "docs/CONTRIBUTING.md": "VirtualGlove-Contributing.pdf",
    "docs/GAMEPLAY_GUIDE.md": "VirtualGlove-Gameplay-Guide.pdf",
    "docs/power-glove-rom-input-audit.md": "VirtualGlove-Input-Audit.pdf",
    "docs/super-glove-ball-native.md": "VirtualGlove-Super-Glove-Ball-Native.pdf",
    "docs/direction-response-benchmark.md": "VirtualGlove-Direction-Response.pdf",
}


def check_native_component_record(errors: list[str]) -> None:
    """Keep the pinned Nestopia source and local patch tied to their notices."""
    build = (ROOT / "scripts/build-nestopia-powerglove.sh").read_text()
    match = re.search(r"^revision=([0-9a-f]{40})$", build, re.MULTILINE)
    if not match:
        errors.append("Nestopia build script has no exact 40-character revision pin")
        return
    revision = match.group(1)
    patch = ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch"
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    records = {
        "third-party notices": ROOT / "THIRD_PARTY_NOTICES.md",
    }
    for label, path in records.items():
        if revision not in path.read_text():
            errors.append(f"Nestopia revision is missing from {label}: {path.relative_to(ROOT)}")
    for path in records.values():
        if digest not in path.read_text():
            errors.append(f"Nestopia patch SHA-256 is stale or missing: {path.relative_to(ROOT)}")


def check_extra_digit_hunt(errors: list[str]) -> None:
    """Keep the playful published answers synchronized with visible artwork."""
    path = ROOT / "docs/extra-digit-hunt.json"
    try:
        manifest = json.loads(path.read_text())
        guides = manifest["guides"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read Extra-Digit Hunt manifest: {exc}")
        return
    for filename, guide in guides.items():
        source_path = ROOT / "docs" / filename
        try:
            source = source_path.read_text()
            answer = int(guide["answer"])
            images = guide["images"]
            locations = guide["locations"]
        except (OSError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid Extra-Digit Hunt guide record for {filename}: {exc}")
            continue
        calculated = 0
        tags = re.findall(r"<img\s+[^>]+>", source, re.IGNORECASE)
        listed_images = set(images)
        described_images = set()
        for tag in tags:
            if "six-digit" not in tag.lower():
                continue
            match = re.search(r'src="([^"]+)"', tag, re.IGNORECASE)
            if match:
                described_images.add(match.group(1))
        for image in sorted(described_images - listed_images):
            errors.append(
                f"Extra-Digit Hunt image is described as six-digit but is not in the manifest: "
                f"{image} in {filename}"
            )
        for image, record in images.items():
            expected = int(record["occurrences"])
            hands = int(record["hands_per_appearance"])
            matches = [tag for tag in tags if f'src="{image}"' in tag]
            if len(matches) != expected:
                errors.append(
                    f"Extra-Digit Hunt expected {expected} uses of {image} in {filename}; "
                    f"found {len(matches)}"
                )
            if any("six-digit" not in tag.lower() for tag in matches):
                errors.append(f"Extra-Digit Hunt accessibility text is missing for {image} in {filename}")
            calculated += len(matches) * hands
        if calculated != answer:
            errors.append(
                f"Extra-Digit Hunt answer for {filename} is {answer}; artwork totals {calculated}"
            )
        if len(locations) != answer or len(set(locations)) != len(locations):
            errors.append(
                f"Extra-Digit Hunt locations for {filename} must name all {answer} hands exactly once"
            )
        if f"**Pixel Pal's answer: {answer} six-digit hands.**" not in source:
            errors.append(f"Extra-Digit Hunt published answer is stale in {filename}")
        if "Count every six-digit hand once per appearance" not in source:
            errors.append(f"Extra-Digit Hunt instructions are missing from {filename}")


def tracked_markdown() -> list[Path]:
    """Return present tracked and new nonignored Markdown files in stable order."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "*.md"], cwd=ROOT
    ).decode().split("\0")
    return sorted(Path(name) for name in output if name and (ROOT / name).is_file())


def local_targets(path: Path) -> list[Path]:
    """Extract repository-local Markdown and HTML link targets from one document."""
    text = (ROOT / path).read_text()
    targets = [*MARKDOWN_LINK.findall(text), *HTML_LINK.findall(text)]
    resolved = []
    for raw in targets:
        value = raw.strip().strip("<>").split(maxsplit=1)[0]
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or value.startswith(("#", "/")):
            continue
        relative = unquote(parsed.path)
        if relative:
            resolved.append(path.parent / relative)
    return resolved


def check_pdfs(errors: list[str]) -> None:
    """Verify the exact PDF set, readable text, and absence of renderer placeholders."""
    try:
        from pypdf import PdfReader
    except ImportError:
        errors.append("pypdf is required for --require-pdfs")
        return
    output = ROOT / "output" / "pdf"
    expected = set(PDF_EDITIONS.values())
    present = {path.name for path in output.glob("*.pdf")}
    for name in sorted(expected - present):
        errors.append(f"missing PDF edition: output/pdf/{name}")
    for name in sorted(present - expected):
        errors.append(f"unregistered PDF edition: output/pdf/{name}")
    for name in sorted(expected & present):
        path = output / name
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        if len(text) < 500:
            errors.append(f"PDF has unexpectedly little extractable text: {path.relative_to(ROOT)}")
        if "@@TOKEN" in text:
            errors.append(f"PDF contains unresolved renderer placeholder: {path.relative_to(ROOT)}")


def check_help_coverage(markdown: list[Path], errors: list[str]) -> None:
    """Require every portable guide to appear in the built-in Help library."""
    source = (ROOT / "src" / "powerglove_vision" / "help_content.py").read_text()
    help_files = set(HELP_FILE.findall(source))
    portable_guides = {
        path.name
        for path in markdown
        if path.parent == Path("docs") and path.name != "cheatsheet.md"
    }
    for name in sorted(portable_guides - help_files):
        errors.append(f"public guide is missing from the Help library: docs/{name}")


def check_gameplay_coverage(errors: list[str]) -> None:
    """Require every registered title family to appear in the gameplay guide."""
    try:
        registry = json.loads((ROOT / "config" / "games.json").read_text())["games"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot check gameplay coverage: {exc}")
        return
    gameplay = (ROOT / "docs" / "GAMEPLAY_GUIDE.md").read_text()
    titles = {re.sub(r"\s*\([^)]*\)", "", Path(filename).stem).strip()
              for filename in registry}
    title_aliases = {
        "1943 - The Battle of Midway": "1943",
        "Iron Tank - The Invasion of Normandy": "Iron Tank",
    }
    def normalize_title(value):
        """Normalize registered ROM filenames to handbook game titles."""
        return re.sub(r"[^a-z0-9]", "", value.lower())
    normalized_gameplay = normalize_title(gameplay)
    for title in sorted(titles):
        display_title = title_aliases.get(title, title)
        if normalize_title(display_title) not in normalized_gameplay:
            errors.append(f"registered game is missing from the gameplay guide: {title}")


def build_parser() -> argparse.ArgumentParser:
    """Create the documentation-audit command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-pdfs",
        action="store_true",
        help="also require and inspect every registered PDF edition",
    )
    return parser


def main() -> int:
    """Run documentation checks and return a CI-friendly process status."""
    args = build_parser().parse_args()
    errors: list[str] = []
    check_native_component_record(errors)
    check_extra_digit_hunt(errors)
    markdown = tracked_markdown()
    for path in markdown:
        # Distribution-wide licensing notices stay beside the root LICENSE.
        if path not in {
            Path("README.md"), Path("THIRD_PARTY_NOTICES.md"),
        } and path.parts[0] != "docs":
            errors.append(f"project Markdown must be under docs/: {path}")
        for target in local_targets(path):
            if not (ROOT / target).exists():
                errors.append(f"broken local link in {path}: {target}")

    check_help_coverage(markdown, errors)
    check_gameplay_coverage(errors)

    reference = (ROOT / "docs" / "CONFIGURATION_REFERENCE.md").read_text()
    for name in CONFIGURATION_FILES:
        if name not in reference:
            errors.append(f"configuration reference does not describe {name}")
    for path in sorted((ROOT / "config").glob("*.json")):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")

    markdown_sources = {str(path) for path in markdown}
    missing_sources = sorted(set(PDF_EDITIONS) - markdown_sources)
    for name in missing_sources:
        errors.append(f"PDF source is not available Markdown: {name}")
    missing_editions = sorted(markdown_sources - set(PDF_EDITIONS))
    for name in missing_editions:
        errors.append(f"maintained Markdown has no registered PDF edition: {name}")
    if args.require_pdfs:
        check_pdfs(errors)

    if errors:
        print("\n".join(errors))
        return 1
    suffix = " and PDF editions" if args.require_pdfs else ""
    print(f"Documentation audit passed for {len(markdown)} Markdown files{suffix}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
