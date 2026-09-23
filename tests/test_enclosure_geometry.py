#!/usr/bin/env python3
# Project: VirtualGlove
# File: tests/test_enclosure_geometry.py
# Purpose: Protect enclosure dimensions and physical-fit corrections.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-20 - Added regression coverage for printed enclosure fit.
# Full history: docs/CHANGELOG.md and Git history.

"""Protect the enclosure dimensions and the physical-fit corrections."""

from __future__ import annotations

from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parent.parent
ENCLOSURE = ROOT / "hardware/enclosures"
SOURCE = ENCLOSURE / "virtualglove-controller.scad"


def stl_size(path: Path) -> tuple[float, float, float]:
    """Return the axis-aligned size of a binary STL."""
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + count * 50:
        raise ValueError(f"not a binary STL: {path}")
    axes = [[], [], []]
    for triangle in range(count):
        values = struct.unpack_from("<12fH", data, 84 + triangle * 50)
        for vertex in range(3):
            for axis in range(3):
                axes[axis].append(values[3 + vertex * 3 + axis])
    return tuple(max(axis) - min(axis) for axis in axes)


class EnclosureGeometryTests(unittest.TestCase):
    def test_lid_skirts_clear_bosses_and_usb_c_opening(self):
        source = SOURCE.read_text()
        self.assertIn("lid_boss_relief_d = 9.2", source)
        self.assertIn("d = lid_boss_relief_d", source)
        self.assertEqual(source.count("lid_usb_c_relief("), 3)
        self.assertIn("cube([wall + fit + 4.0, 31.0", source)

    def test_board_supports_clear_bottom_connectors(self):
        source = SOURCE.read_text()
        self.assertIn("uno_standoff_d = 5.4", source)
        self.assertIn("uno_standoff_foot_d = 6.4", source)
        self.assertIn("uno_standoff_foot_h = 1.6", source)

    def test_v21_uses_photo_validated_clearances(self):
        source = SOURCE.read_text()
        self.assertIn("dock_v21_w = 172", source)
        self.assertIn("dock_v21_uno_x = 76.0", source)
        self.assertIn("hub_v21_rear_gap = 14.0", source)
        self.assertIn("hub_v21_y + hub_w + 1.5 < dock_v21_d - 6.3 - 4.0", source)
        self.assertIn("v21_lid_skirt_h = 3.2", source)
        self.assertIn("v21_lid_boss_relief_d = 11.0", source)
        self.assertIn("v21_standoff_d = 4.8", source)
        self.assertIn("v21_full_wordmark_recess = [102.0, 32.0]", source)
        self.assertIn("cable_guides_v21();", source)

    def test_wordmark_recesses_match_the_printed_logo_sizes(self):
        source = SOURCE.read_text()
        self.assertIn("uno_wordmark_recess = [60.5, 18.5]", source)
        self.assertIn("full_wordmark_recess = [100.8, 30.8]", source)
        self.assertEqual(source.count("full_wordmark_recess);"), 2)
        self.assertIn("v21_full_wordmark_recess = [102.0, 32.0]", source)
        self.assertEqual(source.count("uno_wordmark_recess);"), 1)

    def test_compact_uno_fasteners_clear_the_board(self):
        # Check both narrow PCB-to-wall strips. The M3 insert bosses must not
        # touch the UNO Q, including ordinary PLA fit variation.
        width, depth = 80.0, 69.0
        board_width, board_depth = 68.58, 53.34
        board_y = (depth - board_depth) / 2
        boss_radius = 6.5 / 2
        self.assertGreater(board_y - (3.5 + boss_radius), 1.0)
        self.assertGreater((depth - 3.5 - boss_radius) -
                           (board_y + board_depth), 1.0)
        self.assertGreater((width - board_width) / 2 - 2.4, 3.0)

    def test_exported_lids_match_their_bases(self):
        expected = {
            "uno": (80.0, 69.0, 21.0, 5.6),
            "dock": (148.0, 104.0, 25.0, 8.4),
            "dock-v2-1": (172.0, 126.0, 38.0, 5.6),
        }
        for stem, (width, depth, base_height, lid_height) in expected.items():
            with self.subTest(stem=stem):
                base = stl_size(ENCLOSURE / "stl" / f"virtualglove-{stem}-base.stl")
                lid = stl_size(ENCLOSURE / "stl" / f"virtualglove-{stem}-lid.stl")
                self.assertEqual(tuple(round(value, 2) for value in base),
                                 (width, depth, base_height))
                self.assertEqual(tuple(round(value, 2) for value in lid),
                                 (width, depth, lid_height))

    def test_uno_wordmark_fits_its_lid(self):
        backing = stl_size(ENCLOSURE / "stl/virtualglove-uno-wordmark-backing.stl")
        self.assertEqual(tuple(round(value, 2) for value in backing),
                         (60.0, 18.0, 0.8))

    def test_exporter_has_apple_silicon_headless_fallback(self):
        script = (ENCLOSURE / "export-stl.sh").read_text()
        self.assertIn("arch -x86_64", script)
        self.assertIn("OPENSCAD_COMMAND", script)
        self.assertIn("OpenSCAD did not create", script)
        self.assertIn('mv "${temporary}" "${target}"', script)


if __name__ == "__main__":
    unittest.main()
