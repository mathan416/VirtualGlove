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
        self.assertEqual(facts["candidate_tag"], "v" + facts["project_version"] + "-rc.1")
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
        ))
        self.assertIn("v0.5.0-rc.1", combined)
        self.assertNotIn("v0.4.1", combined)
        self.assertNotIn("Get ready to play", combined)
        about = (dist / "about.html").read_text()
        self.assertIn("Where it started", about)
        self.assertIn("Timex Sinclair 1000", about)
        self.assertIn("Commodore 64", about)
        self.assertIn("Amiga 500", about)
        self.assertIn("degree in Computer Science", about)
        self.assertIn("emulator behaviour", about)
        self.assertIn("labour of love", about)
        self.assertIn("recognises its movement", about)
        home = (dist / "index.html").read_text()
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
