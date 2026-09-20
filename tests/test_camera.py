# Project: VirtualGlove
# File: tests/test_camera.py
# Purpose: Verify camera discovery, filtering, stable paths, and explicit device selection.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify camera discovery, filtering, stable paths, and explicit device selection."""

import tempfile
import unittest
from pathlib import Path

from virtualglove.camera import (
    camera_candidates, camera_device_identity, camera_device_options,
    discover_camera_devices,
)


def _video_device(dev: Path, sys: Path, index: int, name: str, interface_index: str = "0") -> Path:
    node = dev / f"video{index}"
    node.touch()
    metadata = sys / node.name
    metadata.mkdir(parents=True)
    (metadata / "name").write_text(name)
    (metadata / "index").write_text(interface_index)
    return node


class CameraDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dev = self.root / "dev"
        self.sys = self.root / "sys" / "class" / "video4linux"
        self.dev.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_auto_discovery_ignores_uno_q_codec_nodes(self) -> None:
        _video_device(self.dev, self.sys, 0, "Qualcomm Venus video encoder")
        _video_device(self.dev, self.sys, 1, "Qualcomm Venus video decoder")

        self.assertEqual(discover_camera_devices(self.dev, self.sys), [])
        self.assertEqual(camera_candidates("auto", self.dev, self.sys), [])

    def test_auto_discovery_finds_only_primary_usb_video_interface(self) -> None:
        camera = _video_device(self.dev, self.sys, 2, "Razer Kiyo", "0")
        _video_device(self.dev, self.sys, 3, "Razer Kiyo", "1")

        self.assertEqual(discover_camera_devices(self.dev, self.sys), [camera])

    def test_stable_usb_camera_path_is_preferred_and_not_duplicated(self) -> None:
        camera = _video_device(self.dev, self.sys, 4, "Razer Kiyo")
        by_id = self.dev / "v4l" / "by-id"
        by_id.mkdir(parents=True)
        stable = by_id / "usb-Razer_Kiyo-video-index0"
        stable.symlink_to(camera)

        self.assertEqual(discover_camera_devices(self.dev, self.sys), [stable])

    def test_browser_options_are_labelled_numeric_devices_with_auto_first(self) -> None:
        camera = _video_device(self.dev, self.sys, 4, "  Razer   Kiyo Pro  ")
        by_id = self.dev / "v4l" / "by-id"
        by_id.mkdir(parents=True)
        (by_id / "usb-Razer_Kiyo_Pro-video-index0").symlink_to(camera)

        self.assertEqual(camera_device_options(self.dev, self.sys), [
            {"value": "auto", "label": "Automatic — choose the connected camera"},
            {"value": "4", "label": "Razer Kiyo Pro — camera 4"},
        ])

    def test_explicit_camera_index_is_preserved(self) -> None:
        self.assertEqual(camera_candidates("7", self.root, self.root), [7])

    def test_camera_identity_is_stable_and_contains_no_serial(self) -> None:
        camera = _video_device(self.dev, self.sys, 4, "Razer Kiyo Pro")
        usb = self.root / "usb" / "2-1"
        usb.mkdir(parents=True)
        (usb / "idVendor").write_text("1532\n")
        (usb / "idProduct").write_text("0E05\n")
        (usb / "serial").write_text("private-camera-serial\n")
        (self.sys / "video4" / "device").symlink_to(usb, target_is_directory=True)

        identity = camera_device_identity("4", self.dev, self.sys)

        self.assertEqual(identity["vendor_id"], "1532")
        self.assertEqual(identity["product_id"], "0e05")
        self.assertTrue(identity["has_serial"])
        self.assertNotIn("private-camera-serial", str(identity))
        self.assertEqual(identity, camera_device_identity("4", self.dev, self.sys))


if __name__ == "__main__":
    unittest.main()
