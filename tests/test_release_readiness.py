# Project: VirtualGlove
# File: tests/test_release_readiness.py
# Purpose: Protect centralized release facts, website output, and enclosure bundles.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-20 - Added 0.5.0 documentation and public-site release checks.
# Full history: docs/CHANGELOG.md and Git history.
"""Test release-sensitive public artifacts without contacting external services."""

from __future__ import annotations

import json
import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    """Keep generated public artifacts tied to the checked release facts."""

    def test_release_facts_match_python_package(self):
        facts = json.loads((ROOT / "config/release.json").read_text())
        project = (ROOT / "pyproject.toml").read_text()
        version = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), facts["project_version"])
        self.assertEqual(facts["release_tag"], "v" + facts["project_version"])
        self.assertEqual(facts["channel"], "stable")
        self.assertEqual(facts["oldest_supported_upgrade"], "v0.4.2")
        self.assertEqual(facts["upgrade_acceptance"], {
            "from": "v0.4.2",
            "status": "passed",
            "confirmed_on": "2026-09-20",
            "scope": "Controller and applicable consoles",
        })

    def test_generated_website_matches_upload_zip(self):
        dist = ROOT / "website/dist"
        archive = ROOT / "output/website/VirtualGlove-Website.zip"
        expected = {
            path.relative_to(dist).as_posix(): path.read_bytes()
            for path in dist.rglob("*")
            if path.is_file() and path.name != ".DS_Store"
        }
        with zipfile.ZipFile(archive) as package:
            actual = {name: package.read(name) for name in package.namelist()}
        self.assertEqual(actual, expected)
        combined = "\n".join((dist / name).read_text() for name in (
            "index.html", "install.html", "build.html", "about.html",
            "engineering.html",
        ))
        self.assertIn("v0.5.1", combined)
        self.assertNotIn("v0.5.1-rc.1", combined)
        self.assertNotIn("v0.4.1", combined)
        self.assertNotIn("Get ready to play", combined)
        about = (dist / "about.html").read_text()
        self.assertIn("Where it started", about)
        self.assertIn("Timex Sinclair 1000", about)
        self.assertIn("Commodore 64", about)
        self.assertIn("Amiga 500", about)
        self.assertIn("degree in Computer Science", about)
        self.assertIn("late 1970s and early 1980s", about)
        self.assertIn("logic chips and LEDs", about)
        self.assertIn("explored gesture and voice recognition", about)
        self.assertIn("That was the light-bulb moment", about)
        self.assertIn("a wonderfully strange side quest in retrogaming history", about)
        self.assertIn("emulator behaviour", about)
        self.assertIn("labour of love", about)
        self.assertIn("recognises its movement", about)
        self.assertIn("iain-virtualglove-recognition.jpg", about)
        self.assertIn("Iain tests Super Glove Ball while VirtualGlove recognises his hand", about)
        self.assertIn("assets/iain-virtualglove-recognition.jpg", actual)
        home = (dist / "index.html").read_text()
        self.assertIn("Stable release · v0.5.1", home)
        self.assertIn("current stable release", home)
        self.assertIn("Learn to play in Glove Academy", home)
        self.assertIn("how VirtualGlove recognises your hand movements and gestures", home)
        self.assertNotIn("Learn safely in Glove Academy", home)
        self.assertIn("virtualglove-controller-camera.jpg", home)
        self.assertIn("virtualglove-gameplay-poster.jpg", home)
        self.assertIn("virtualglove-gameplay.mp4", home)
        self.assertIn("<video controls playsinline", home)
        for media in (
            "assets/virtualglove-controller-camera.jpg",
            "assets/virtualglove-gameplay-poster.jpg",
            "assets/virtualglove-gameplay.mp4",
        ):
            self.assertIn(media, actual)
        install = (dist / "install.html").read_text()
        self.assertIn("Use the same commands for a fresh installation or an upgrade", install)
        self.assertIn("There is no separate upgrade command", install)
        self.assertIn("Rerun the same Controller and console commands shown above", install)
        build = (dist / "build.html").read_text()
        self.assertIn("Before you print", build)
        self.assertNotIn("Print safely", build)
        self.assertIn('class="shell actions build-actions"', build)
        self.assertIn("not installed in the finished case", build)
        engineering = (dist / "engineering.html").read_text()
        self.assertIn("Engineering, explained", engineering)
        for guide in (
            "ARCHITECTURE.md", "INPUT_MODES.md", "CONFIGURATION_REFERENCE.md",
            "ENGINEERING_TOOLKIT.md", "ENGINEERING_JOURNEY.md",
            "power-glove-rom-input-audit.md", "SECURITY.md", "CONTRIBUTING.md",
            "CHANGELOG.md", "NATIVE_EMULATION_EXPLAINED.md",
            "super-glove-ball-native.md", "direction-response-benchmark.md",
        ):
            self.assertIn(guide, engineering)
        for page in ("index.html", "install.html", "build.html", "about.html"):
            self.assertIn('href="engineering.html"', (dist / page).read_text())
        styles = (dist / "assets/site.css").read_text()
        self.assertIn(".case{display:flex;flex-direction:column}", styles)
        self.assertIn(".case .button{align-self:flex-start;margin-top:auto}", styles)
        self.assertIn(".build-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))", styles)
        self.assertIn(".build-actions .button{display:flex;align-items:center;justify-content:center", styles)

    def test_website_upload_is_separate_from_release_assets(self):
        builder = (ROOT / "scripts/build-install-packages.py").read_text()
        workflow = (ROOT / ".github/workflows/install-release.yml").read_text()
        self.assertNotIn('runpy.run_path(str(ROOT / "website/build.py"))', builder)
        self.assertIn('stale_website = destination / "VirtualGlove-Website.zip"', builder)
        self.assertIn("output/install/SHA256SUMS", workflow)
        self.assertNotIn('gh release create "$RELEASE_VERSION" output/install/*', workflow)
        self.assertIn('gh release create "$RELEASE_VERSION" "${release_assets[@]}" --draft', workflow)
        self.assertLess(workflow.index('gh release download "$RELEASE_VERSION"'),
                        workflow.index('sha256sum --check SHA256SUMS'))
        self.assertLess(workflow.index('sha256sum --check SHA256SUMS'),
                        workflow.index('gh release edit "$RELEASE_VERSION" --repo "$GITHUB_REPOSITORY" --draft=false'))

    def test_enclosure_manifest_covers_every_public_print_file(self):
        root = ROOT / "hardware/enclosures"
        data = json.loads((root / "enclosure-files.json").read_text())
        classified = {value for value in data["shared"].values()
                      if value.startswith("stl/")}
        for group in data["branding"].values():
            classified.update(group)
        for design in data["designs"].values():
            classified.update(design["structural"])
            with zipfile.ZipFile(root / "bundles" / design["archive"]) as package:
                names = package.namelist()
            self.assertIn("PARTS.txt", names)
            self.assertFalse(any("target-badge" in name for name in names))
        present = {"stl/" + path.name for path in (root / "stl").iterdir()
                   if path.suffix.lower() in (".stl", ".3mf")}
        self.assertEqual(classified, present)


if __name__ == "__main__":
    unittest.main()
