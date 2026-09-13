# Project: VirtualGlove
# File: tests/test_unoq_camera_recovery_helper.py
# Purpose: Verify first-use camera enrollment and guarded parent-hub recovery.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Verify recovery cannot reset a network-bearing USB hub.
#   2026-09-09 - Covered capability-gated camera-port cycling and schema migration.
#   2026-09-08 - Verify present-but-wedged camera recovery and request validation.
#   2026-09-05 - Added isolated helper enrollment, hub-move and reset tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify root-helper enrollment and guarded hub recovery in a temporary tree."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "powerglove_camera_recovery_helper",
    ROOT / "uno-q" / "virtualglove-camera-recovery.py",
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class UnoQCameraRecoveryHelperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.driver = self.root / "driver"
        self.driver.mkdir()
        (self.driver / "unbind").touch()
        (self.driver / "bind").touch()
        self.lock = self.root / "lock"
        self.stamp = self.root / "stamp"
        self.config = self.root / "camera.json"
        self.request = self.data / "camera-recovery-request"
        self.result = self.data / "camera-recovery-result"
        self.usb_devices = self.root / "usb-devices"
        self.usb_devices.mkdir()
        self.patchers = [
            patch.object(helper, "APP_DATA", self.data),
            patch.object(helper, "REQUEST", self.request),
            patch.object(helper, "RESULT", self.result),
            patch.object(helper, "USB_DEVICES", self.usb_devices),
            patch.object(helper, "USB_DRIVER", self.driver),
            patch.object(helper, "CONFIG", self.config),
            patch.object(helper, "LOCK", self.lock),
            patch.object(helper, "STAMP", self.stamp),
            patch.object(helper, "_config_is_secure", return_value=True),
            patch.object(helper.shutil, "which", return_value=None),
            patch.object(helper.os, "geteuid", return_value=0),
            patch.object(helper.time, "sleep"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def device(self, name):
        path = self.root / name
        (path / "power").mkdir(parents=True)
        (path / "power" / "control").write_text("auto")
        return path

    def discovery(self, camera, hub, camera_id=("1532", "0e05"), hub_id=("0bda", "0411")):
        return {
            "camera": {"vendor_id": camera_id[0], "product_id": camera_id[1], "name": "Test camera"},
            "hub": {
                "vendor_id": hub_id[0],
                "product_id": hub_id[1],
                "name": "Test hub",
                "sysfs_name": hub.name,
            },
            "camera_path": camera,
            "hub_path": hub,
        }

    def install_hub_link(self, hub, hub_id=("0bda", "0411")):
        (hub / "idVendor").write_text(hub_id[0])
        (hub / "idProduct").write_text(hub_id[1])
        (hub / "bDeviceClass").write_text("09")
        (self.usb_devices / hub.name).symlink_to(hub)

    def test_discovers_one_video_camera_and_its_nearest_external_hub(self):
        devices = self.root / "sys-devices" / "usb2"
        hub = devices / "2-1"
        camera = hub / "2-1.4"
        interface = camera / "2-1.4:1.0"
        video = interface / "video4linux" / "video1"
        video.mkdir(parents=True)
        for device, identity, device_class, product in (
            (hub, ("0bda", "0411"), "09", "Example powered hub"),
            (camera, ("046d", "0825"), "ef", "Example UVC camera"),
        ):
            (device / "idVendor").write_text(identity[0])
            (device / "idProduct").write_text(identity[1])
            (device / "bDeviceClass").write_text(device_class)
            (device / "product").write_text(product)
        (video / "index").write_text("0")
        (video / "name").write_text("Example UVC camera: Capture")
        (video / "device").symlink_to(interface)
        video_class = self.root / "video-class"
        video_class.mkdir()
        (video_class / "video1").symlink_to(video)
        with patch.object(helper, "VIDEO_CLASS", video_class):
            discovered = helper._discover_cameras()
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["camera"]["vendor_id"], "046d")
        self.assertEqual(discovered[0]["hub"]["sysfs_name"], "2-1")

    def test_installer_defers_enrollment_when_camera_is_absent(self):
        with patch.object(helper, "_discover_cameras", return_value=[]):
            self.assertEqual(helper.main(["--configure-if-present"]), 0)
        self.assertFalse(self.config.exists())

    def test_first_healthy_camera_is_enrolled_and_kept_awake(self):
        camera = self.device("2-1.4")
        hub = self.device("2-1")
        self.request.write_text("enroll\n")
        with patch.object(helper, "_discover_cameras", return_value=[self.discovery(camera, hub)]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual(
            json.loads(self.result.read_text())["status"], "usb-action-complete"
        )
        saved = json.loads(self.config.read_text())
        self.assertEqual(saved["schema"], 2)
        self.assertEqual(saved["camera"]["vendor_id"], "1532")
        self.assertEqual(saved["camera"]["hub_port"], "4")
        self.assertEqual(saved["hub"]["sysfs_name"], "2-1")
        self.assertEqual((camera / "power" / "control").read_text(), "on")
        self.assertEqual((hub / "power" / "control").read_text(), "on")
        self.assertEqual((self.driver / "unbind").read_text(), "")

    def test_healthy_camera_moved_to_another_hub_updates_enrollment(self):
        old_camera = self.device("2-1.4")
        old_hub = self.device("2-1")
        helper._write_config(self.discovery(old_camera, old_hub))
        new_camera = self.device("4-2.3")
        new_hub = self.device("4-2")
        self.request.write_text("enroll\n")
        with patch.object(helper, "_discover_cameras", return_value=[self.discovery(new_camera, new_hub)]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual(json.loads(self.config.read_text())["hub"]["sysfs_name"], "4-2")

    def test_absent_camera_resets_only_the_last_observed_hub(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        discovery = self.discovery(camera, hub)
        helper._write_config(discovery)
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", side_effect=[[], [discovery]]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual((self.driver / "unbind").read_text(), "2-1")
        self.assertEqual((self.driver / "bind").read_text(), "2-1")
        self.assertEqual((camera / "power" / "control").read_text(), "on")

    def test_enumerated_camera_with_failed_stream_resets_its_hub(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        discovery = self.discovery(camera, hub)
        helper._write_config(discovery)
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", side_effect=[[discovery], [discovery]]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual((self.driver / "unbind").read_text(), "2-1")
        self.assertEqual((self.driver / "bind").read_text(), "2-1")

    def test_refuses_whole_hub_fallback_when_hub_carries_networking(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        network = hub / "2-1.2:1.0" / "net" / "eth0"
        network.mkdir(parents=True)
        discovery = self.discovery(camera, hub)
        helper._write_config(discovery)
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", return_value=[discovery]):
            with self.assertRaisesRegex(RuntimeError, "carries a network interface"):
                helper.main([])
        self.assertEqual((self.driver / "unbind").read_text(), "")
        self.assertEqual((self.driver / "bind").read_text(), "")
        self.assertEqual(json.loads(self.result.read_text())["status"], "failed")

    def test_supported_hub_power_cycles_only_the_enrolled_camera_port(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        discovery = self.discovery(camera, hub)
        helper._write_config(discovery)
        self.request.write_text("recover\n")
        with patch.object(
                helper, "_discover_cameras", side_effect=[[discovery], [discovery]]), \
                patch.object(helper, "_power_cycle_camera_port", return_value=True) as cycle:
            self.assertEqual(helper.main([]), 0)
        cycle.assert_called_once()
        self.assertEqual((self.driver / "unbind").read_text(), "")
        result = json.loads(self.result.read_text())
        self.assertEqual(result["status"], "usb-action-complete")
        self.assertEqual(result["method"], "port-power-cycle")

    def test_uhubctl_probe_requires_exact_supported_hub_output(self):
        supported = SimpleNamespace(
            returncode=0,
            stdout="Current status for hub 2-1 [0bda:0411 USB3.2 Hub]\n  Port 4: 0100 power",
            stderr="",
        )
        with patch.object(helper.subprocess, "run", return_value=supported) as run:
            self.assertTrue(helper._uhubctl_supports_port("/usr/sbin/uhubctl", "2-1", "4"))
        self.assertEqual(
            run.call_args[0][0],
            ["/usr/sbin/uhubctl", "-l", "2-1", "-p", "4", "-e", "-N"],
        )
        unsupported = SimpleNamespace(returncode=0, stdout="No compatible hubs detected", stderr="")
        with patch.object(helper.subprocess, "run", return_value=unsupported):
            self.assertFalse(helper._uhubctl_supports_port("uhubctl", "2-1", "4"))

    def test_port_cycle_uses_only_exact_enrolled_location_and_port(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        config = helper._public_config(self.discovery(camera, hub))
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(helper.shutil, "which", return_value="/usr/sbin/uhubctl"), \
                patch.object(helper, "_uhubctl_supports_port", return_value=True), \
                patch.object(helper.subprocess, "run", return_value=completed) as run:
            self.assertTrue(helper._power_cycle_camera_port(config, hub))
        self.assertEqual(
            run.call_args[0][0],
            [
                "/usr/sbin/uhubctl", "-l", "2-1", "-p", "4", "-e", "-N",
                "-a", "cycle", "-d", "2",
            ],
        )

    def test_recovery_rejects_a_different_camera_after_usb_action(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        enrolled = self.discovery(camera, hub)
        replacement = self.discovery(camera, hub, camera_id=("046d", "0825"))
        helper._write_config(enrolled)
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", side_effect=[[], [replacement]]):
            with self.assertRaisesRegex(RuntimeError, "different camera or hub"):
                helper.main([])
        self.assertEqual(json.loads(self.result.read_text())["status"], "failed")

    def test_version_one_enrollment_safely_uses_whole_hub_fallback(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub)
        discovery = self.discovery(camera, hub)
        legacy = helper._public_config(discovery)
        legacy["schema"] = 1
        legacy["camera"].pop("hub_port")
        self.config.write_text(json.dumps(legacy))
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", side_effect=[[], [discovery]]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual((self.driver / "unbind").read_text(), "2-1")
        self.assertEqual(json.loads(self.result.read_text())["method"], "hub-driver-rebind")

    def test_enumerated_camera_for_enrollment_is_not_reset(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        discovery = self.discovery(camera, hub)
        self.request.write_text("enroll\n")
        with patch.object(helper, "_discover_cameras", return_value=[discovery]):
            self.assertEqual(helper.main([]), 0)
        self.assertEqual((self.driver / "unbind").read_text(), "")

    def test_unknown_request_action_is_rejected_after_consumption(self):
        self.request.write_text("reset-everything\n")
        with self.assertRaisesRegex(RuntimeError, "unknown action"):
            helper.main([])
        self.assertFalse(self.request.exists())

    def test_refuses_hub_when_identity_at_saved_path_has_changed(self):
        hub = self.device("2-1")
        camera = self.device("2-1.4")
        self.install_hub_link(hub, ("1234", "5678"))
        helper._write_config(self.discovery(camera, hub))
        self.request.write_text("recover\n")
        with patch.object(helper, "_discover_cameras", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "absent or has changed identity"):
                helper.main([])
        self.assertEqual((self.driver / "unbind").read_text(), "")

    def test_refuses_ambiguous_first_use(self):
        camera = self.device("2-1.4")
        hub = self.device("2-1")
        self.request.write_text("enroll\n")
        discovery = self.discovery(camera, hub)
        with patch.object(helper, "_discover_cameras", return_value=[discovery, discovery]):
            with self.assertRaisesRegex(RuntimeError, "expected one UVC camera"):
                helper.main([])
        self.assertFalse(self.config.exists())


if __name__ == "__main__":
    unittest.main()
