# Project: VirtualGlove
# File: tests/test_recalbox_assets.py
# Purpose: Verify persistent Recalbox service and Player 1 integration assets.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added Recalbox and Batocera integration asset coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify console service, lifecycle, input-merge, and pairing assets."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RecalboxAssetsTests(unittest.TestCase):
    def test_runtime_entry_points_are_executable(self):
        for relative in (
                "batocera/VirtualGlove",
                "batocera/virtualglove-game",
                "batocera/virtualglove-core-mount"):
            self.assertTrue((ROOT / relative).stat().st_mode & 0o111, relative)

    def test_service_uses_persistent_merged_gamepad_and_receiver(self):
        text = (ROOT / "recalbox/virtualglove-service").read_text()
        self.assertIn("/recalbox/share/system/virtualglove", text)
        self.assertIn("powerglove_vision.$name", text)
        self.assertIn("merged_gamepad serve", text)
        self.assertIn("--output-device merged-gamepad", text)
        self.assertIn("--merged-socket", text)
        self.assertIn('MERGED_SOCKET="$SOCKET_DIR/merged-gamepad.sock"', text)
        self.assertIn('VIRTUALGLOVE_SOCKET_DIR:-/run/virtualglove', text)
        self.assertNotIn('$RUN/merged-gamepad.sock', text)
        self.assertIn("player1-controller.json", text)
        self.assertIn("/run/virtualglove/native-state", text)
        self.assertIn('sh "$CORE_MOUNT" start', text)
        self.assertIn('--receiver-restart-command sh "$0" restart-receiver', text)
        self.assertIn('start-stop-daemon -S -b -m -p "$RUN/$name.pid"', text)
        self.assertIn('-x /usr/bin/python3 --', text)
        self.assertIn('</dev/null >> "$LOG/$name.log" 2>&1', text)
        self.assertIn("powerglove_vision.pairing", text)
        self.assertIn("--receiver-restart-command", text)
        self.assertNotIn("systemctl", text)
        self.assertNotIn("/etc/virtualglove", text)

    def test_nes_override_is_runtime_managed_without_keyboard_bindings(self):
        text = (ROOT / "recalbox/retroarch-nes.cfg").read_text()
        for key in ("a", "b", "start", "select", "up", "down", "left", "right"):
            self.assertNotIn("input_player1_" + key + " = ", text)
        self.assertIn("merged Player 1", text)

    def test_recalbox_native_core_overlay_is_separate_and_reloads_frontend_once(self):
        text = (ROOT / "recalbox/virtualglove-core-mount").read_text()
        self.assertIn("nestopia_powerglove_libretro.so", text)
        self.assertIn("verify-recalbox-native-core.py", text)
        self.assertIn("retaining FCEUmm joystick mode", text)
        self.assertIn("mount -t overlay", text)
        self.assertIn('mount --bind "$SYSTEM_RUNTIME" "$SYSTEM_TARGET"', text)
        self.assertIn("S31emulationstation restart", text)
        self.assertNotIn('nestopia_libretro.so" "$CORE_TARGET', text)

    def test_batocera_uses_supported_service_and_game_event_adapters(self):
        service = (ROOT / "batocera/VirtualGlove").read_text()
        event = (ROOT / "batocera/virtualglove-game").read_text()
        self.assertIn("VIRTUALGLOVE_MONITOR=0", service)
        self.assertIn("VIRTUALGLOVE_NATIVE_STATE=/run/virtualglove/native-state", service)
        self.assertIn('VIRTUALGLOVE_CORE_MOUNT="$core_mount"', service)
        self.assertIn("virtualglove-core-mount", service)
        self.assertIn("/userdata/system/virtualglove", service)
        self.assertIn("gameStart", event)
        self.assertIn("gameStop", event)
        self.assertIn('emulator="lr-${4:-}"', event)
        self.assertIn('nestopia_powerglove) emulator="lr-nestopia-powerglove"', event)
        self.assertNotIn("systemctl", service + event)

    def test_batocera_native_core_overlay_is_separate_and_reversible(self):
        text = (ROOT / "batocera/virtualglove-core-mount").read_text()
        self.assertIn("nestopia_powerglove_libretro.so", text)
        self.assertIn("nestopia_powerglove_libretro.info", text)
        self.assertIn("mount -t overlay", text)
        self.assertIn('mount --bind "$merged" "$lower"', text)
        self.assertIn('unmount_one "$CORE_TARGET"', text)
        self.assertNotIn("cp \"$CORE\" \"$CORE_TARGET", text)

    def test_ssh_pairing_uses_each_console_persistent_token_and_root_needs_no_sudo(self):
        text = (ROOT / "python/ssh_pair.py").read_text()
        self.assertIn('os.path.isfile("/recalbox/recalbox.version")', text)
        self.assertIn('os.path.isfile("/usr/share/batocera/batocera.version")', text)
        self.assertIn('os.makedirs(os.path.dirname(destination)', text)
        self.assertIn('str(request["username"]) == "root"', text)
        self.assertIn('selected platform does not match this console', text)
        self.assertIn('"sh", "/recalbox/share/system/virtualglove/recalbox/virtualglove-service"', text)
        self.assertIn('"/userdata/system/services/VirtualGlove", "restart-receiver"', text)
        self.assertNotIn('os.makedirs("/etc/virtualglove"', text)


if __name__ == "__main__":
    unittest.main()
