# Project: VirtualGlove
# File: tests/test_merged_gamepad.py
# Purpose: Verify generic Recalbox/Batocera merged Player 1 behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Covered a two-gamepad I-PAC with one shared USB identity.
#   2026-09-16 - Added merged Player 1 selection and arbitration coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify generic Recalbox/Batocera merged Player 1 behavior."""

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from virtualglove import merged_gamepad as merged


ES_INPUT = """<inputList><inputConfig type="joystick" deviceName="Test Pad" deviceGUID="abc">
<input name="a" type="button" id="0" value="1" code="304"/>
<input name="select" type="button" id="8" value="1" code="314"/>
<input name="hotkey" type="button" id="8" value="1" code="314"/>
<input name="start" type="button" id="9" value="1" code="315"/>
<input name="left" type="hat" id="0" value="8" code="16"/>
<input name="right" type="hat" id="0" value="2" code="16"/>
<input name="up" type="hat" id="0" value="1" code="17"/>
<input name="joystick1left" type="axis" id="0" value="-1" code="0"/>
<input name="pageup" type="button" id="4" value="1" code="310"/>
</inputConfig></inputList>"""


class MergedGamepadTests(unittest.TestCase):
    def test_reads_configured_mapping_and_stable_connected_identity(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            es = root / "es_input.cfg"
            es.write_text(ES_INPUT)
            sys_root = root / "sys"
            base = sys_root / "event4/device"
            (base / "id").mkdir(parents=True)
            (base / "name").write_text("Test Pad\n")
            (base / "capabilities").mkdir()
            (base / "capabilities/key").write_text("1 0\n")
            (base / "id/vendor").write_text("1234\n")
            (base / "id/product").write_text("5678\n")
            (base / "id/version").write_text("0001\n")
            (base / "uniq").write_text("serial\n")
            (base / "phys").write_text("usb-1\n")
            (sys_root / "js0").mkdir()
            (sys_root / "js0/device").symlink_to(base.resolve(), target_is_directory=True)
            candidates = merged.controller_candidates(es, sys_root, root / "dev")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "Test Pad")
        self.assertEqual(candidates[0]["mapping"][0]["code"], 0)
        self.assertEqual(candidates[0]["mapping"][0]["evdev_code"], 304)
        self.assertEqual(candidates[0]["joystick"], str(root / "dev/js0"))
        self.assertEqual(len(candidates[0]["id"]), 16)

    def test_one_ipac_board_exposes_two_distinct_logical_gamepads(self):
        """A shared USB serial must not collapse separate HID collections."""
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            es = root / "es_input.cfg"
            es.write_text(ES_INPUT.replace("Test Pad", "Ultimarc I-PAC Ultimate I/O"))
            sys_root = root / "sys"
            for event_number, js_number, interface in ((0, 0, "input0"), (4, 1, "input2")):
                base = sys_root / f"event{event_number}/device"
                (base / "id").mkdir(parents=True)
                (base / "capabilities").mkdir()
                (base / "name").write_text("Ultimarc I-PAC Ultimate I/O\n")
                (base / "capabilities/key").write_text("1 0\n")
                (base / "id/vendor").write_text("d209\n")
                (base / "id/product").write_text("0412\n")
                (base / "id/version").write_text("0111\n")
                (base / "uniq").write_text("5\n")
                (base / "phys").write_text(
                    f"usb-0000:01:00.0-1.1.1/{interface}\n")
                (sys_root / f"js{js_number}").mkdir()
                (sys_root / f"js{js_number}/device").symlink_to(
                    base.resolve(), target_is_directory=True)
            candidates = merged.controller_candidates(es, sys_root, root / "dev")
        self.assertEqual(len(candidates), 2)
        self.assertEqual({item["phys"].rsplit("/", 1)[-1] for item in candidates},
                         {"input0", "input2"})
        self.assertEqual(len({item["id"] for item in candidates}), 2)

    def test_selection_is_automatic_only_for_one_controller(self):
        one = [{"id": "one", "name": "Only Pad"}]
        self.assertIs(merged.choose_controller(one), one[0])
        with patch.object(merged.os, "isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "--player1-device"):
                merged.choose_controller(one * 2)
        with self.assertRaisesRegex(ValueError, "does not identify"):
            merged.choose_controller(one, requested="missing")

    def test_authoritative_evdev_codes_preserve_keyboard_style_start_select(self):
        mapping = [
            {"name": "b", "type": "button", "code": 4,
             "evdev_code": 304, "value": 1},
            {"name": "a", "type": "button", "code": 5,
             "evdev_code": 305, "value": 1},
            {"name": "select", "type": "button", "code": 0,
             "evdev_code": 139, "value": 1},
            {"name": "start", "type": "button", "code": 1,
             "evdev_code": 158, "value": 1},
            {"name": "hotkey", "type": "button", "code": 2,
             "evdev_code": 172, "value": 1},
        ]
        with patch.object(merged.fcntl, "ioctl", return_value=0):
            translated = merged.translate_es_mapping(mapping, 17)
        self.assertEqual(
            {item["name"]: item["code"] for item in translated},
            {"b": 304, "a": 305, "select": 139, "start": 158, "hotkey": 172},
        )

    def test_retroarch_index_uses_udev_joypad_order_not_js_suffix(self):
        """Batocera's js4 can be RetroArch pad 2 when only three pads exist."""
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            sys_root, udev_root = root / "sys", root / "udev"
            udev_root.mkdir()
            devices = (
                (3, "Keyboard-only controller node", "13:67", False),
                (4, "Physical Player 1", "13:68", True),
                (10, "Virtual spinner", "13:74", True),
                (13, merged.DEVICE_NAME, "13:77", True),
            )
            for number, device_name, device_number, is_joypad in devices:
                event = sys_root / ("event%d" % number)
                (event / "device").mkdir(parents=True)
                (event / "device/name").write_text(device_name + "\n")
                (event / "dev").write_text(device_number + "\n")
                (udev_root / ("c" + device_number)).write_text(
                    "E:ID_INPUT_JOYSTICK=%d\n" % int(is_joypad))
            # The kernel joystick node is deliberately js4; RetroArch sees
            # the same merged event device as the third joypad, index 2.
            (sys_root / "js4/device").mkdir(parents=True)
            (sys_root / "js4/device/name").write_text(merged.DEVICE_NAME + "\n")
            self.assertEqual(merged.merged_joypad_index(sys_root, udev_root), 2)

    def test_retroarch_index_waits_until_udev_marks_merged_device(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            event = root / "sys/event7"
            (event / "device").mkdir(parents=True)
            (event / "device/name").write_text(merged.DEVICE_NAME + "\n")
            (event / "dev").write_text("13:71\n")
            (root / "udev").mkdir()
            self.assertIsNone(merged.merged_joypad_index(root / "sys", root / "udev"))

    def test_saved_identity_handles_port_moves_without_guessing_identical_pads(self):
        serial = {"name": "Pad", "vendor": "1", "product": "2", "version": "3",
                  "uniq": "serial", "phys": "usb-1/input0", "event": "/dev/input/event1"}
        moved = dict(serial, phys="usb-4/input0", event="/dev/input/event9")
        self.assertIs(merged.find_saved_controller(serial, [moved]), moved)
        other_interface = dict(moved, phys="usb-4/input2", event="/dev/input/event10")
        self.assertIs(merged.find_saved_controller(serial, [moved, other_interface]), moved)
        no_serial = dict(serial, uniq="", phys="usb-1")
        only = dict(no_serial, phys="usb-4")
        self.assertIs(merged.find_saved_controller(no_serial, [only]), only)
        duplicate = dict(no_serial, phys="usb-5")
        self.assertIsNone(merged.find_saved_controller(no_serial, [only, duplicate]))

    def test_physical_hotkey_is_separate_and_virtual_select_cannot_enable_it(self):
        mapping = self._mapping()
        state = merged.MergeState()
        state.active = True
        mapper = merged.PhysicalMapper(mapping, state)
        state.virtual = {"buttons": {"select": True, "start": True}}
        buttons, _axes = state.desired()
        self.assertIn("select", buttons)
        self.assertIn("start", buttons)
        self.assertNotIn("hotkey", buttons)
        mapper.event(merged.EV_KEY, 314, 1)
        buttons, _axes = state.desired()
        self.assertIn("hotkey", buttons)
        self.assertIn("select", buttons)

    def test_physical_dpad_and_analog_override_virtual_until_release(self):
        mapping = self._mapping()
        state = merged.MergeState()
        state.active = True
        state.virtual = {"dpad": {"right": True}, "axes": {"x": 12000}}
        mapper = merged.PhysicalMapper(mapping, state)
        mapper.event(merged.EV_ABS, 16, -1)
        mapper.event(merged.EV_ABS, 0, -20000)
        _buttons, axes = state.desired()
        self.assertEqual(axes["hat_x"], -1)
        self.assertEqual(axes["lx"], -20000)
        mapper.event(merged.EV_ABS, 16, 0)
        mapper.event(merged.EV_ABS, 0, 0)
        _buttons, axes = state.desired()
        self.assertEqual(axes["hat_x"], 1)
        self.assertEqual(axes["lx"], 12000)

    def test_physical_direction_owns_only_its_active_axis(self):
        state = merged.MergeState()
        state.active = True
        state.virtual = {"dpad": {"right": True, "down": True}}
        state.physical_axes["hat_y"] = -1
        _buttons, axes = state.desired()
        self.assertEqual((axes["hat_x"], axes["hat_y"]), (1, -1))

    def test_analog_range_is_normalized_and_center_drift_does_not_override_glove(self):
        mapping = self._mapping()
        state = merged.MergeState()
        state.active = True
        state.virtual = {"axes": {"x": 14000}}
        mapper = merged.PhysicalMapper(mapping, state, {0: (0, 255, 2)})
        mapper.event(merged.EV_ABS, 0, 128)
        self.assertEqual(state.desired()[1]["lx"], 14000)
        mapper.event(merged.EV_ABS, 0, 255)
        self.assertEqual(state.desired()[1]["lx"], 32767)
        mapper.event(merged.EV_ABS, 0, 0)
        self.assertEqual(state.desired()[1]["lx"], -32767)

    def test_hat_diagonals_and_positive_analog_travel_follow_es_mapping(self):
        mapping = self._mapping()
        state = merged.MergeState()
        state.active = True
        mapper = merged.PhysicalMapper(mapping, state)
        mapper.event(merged.EV_ABS, 16, -1)
        mapper.event(merged.EV_ABS, 17, -1)
        mapper.event(merged.EV_ABS, 0, 22000)
        mapper.event(merged.EV_KEY, 310, 1)
        buttons, axes = state.desired()
        self.assertEqual((axes["hat_x"], axes["hat_y"]), (-1, -1))
        self.assertEqual(axes["lx"], 22000)
        self.assertIn("l1", buttons)

    def test_disconnect_releases_only_physical_source(self):
        state = merged.MergeState()
        state.active = True
        state.virtual = {"buttons": {"a": True}}
        state.physical_buttons.update(("b", "hotkey"))
        state.physical_axes["hat_x"] = -1
        state.release_physical()
        buttons, axes = state.desired()
        self.assertEqual(buttons, {"a"})
        self.assertEqual(axes["hat_x"], 0)

    def test_output_is_neutral_outside_retroarch(self):
        state = merged.MergeState()
        state.virtual = {"buttons": {"a": True}, "dpad": {"up": True}}
        state.physical_buttons.add("b")
        buttons, axes = state.desired()
        self.assertEqual(buttons, set())
        self.assertTrue(all(value == 0 for value in axes.values()))

    def test_retroarch_migration_removes_only_old_managed_keyboard_lines(self):
        current = ('video_smooth = "false"\ninput_player1_a = "x"\n'
                   'input_player1_b = "custom"\ninput_player1_y = "custom"\ninput_player2_a = "v"\n'
                   'input_player1_joypad_index = "7"\n')
        updated = merged.merge_retroarch_config(current, 2)
        self.assertIn('video_smooth = "false"', updated)
        self.assertIn('input_player1_y = "custom"', updated)
        self.assertIn('input_player2_a = "v"', updated)
        self.assertNotIn('input_player1_a = "x"', updated)
        self.assertIn('input_player1_b = "custom"', updated)
        self.assertIn('input_player1_joypad_index = "2"', updated)
        self.assertIn('input_enable_hotkey_btn = "12"', updated)
        self.assertEqual(merged.merge_retroarch_config(updated, 2), updated)

    def test_recalbox_hotkeys_follow_physical_controls_on_canonical_pad(self):
        mapping = [
            {"name": "b", "type": "button", "code": 0, "value": 1},
            {"name": "a", "type": "button", "code": 1, "value": 1},
            {"name": "x", "type": "button", "code": 2, "value": 1},
            {"name": "y", "type": "button", "code": 3, "value": 1},
            {"name": "l1", "type": "button", "code": 4, "value": 1},
            {"name": "select", "type": "button", "code": 8, "value": 1},
            {"name": "start", "type": "button", "code": 9, "value": 1},
            {"name": "hotkey", "type": "button", "code": 10, "value": 1},
            {"name": "r3", "type": "button", "code": 12, "value": 1},
            {"name": "joystick1left", "type": "axis", "code": 0, "value": -1},
            {"name": "joystick1up", "type": "axis", "code": 1, "value": -1},
            {"name": "l2", "type": "axis", "code": 2, "value": -1},
            {"name": "joystick2left", "type": "axis", "code": 3, "value": -1},
            {"name": "joystick2up", "type": "axis", "code": 4, "value": -1},
            {"name": "r2", "type": "axis", "code": 5, "value": -1},
        ]
        base = "\n".join((
            "input_enable_hotkey_btn = 10", "input_exit_emulator_btn = 9",
            "input_menu_toggle_btn = 0", "input_load_state_btn = 2",
            "input_save_state_btn = 3", "input_screenshot_btn = 4",
            "input_recording_toggle_btn = 12", "input_hold_fast_forward_btn = h0right",
            "input_disk_next_axis = +0", "input_disk_eject_toggle_axis = -1",
            "input_shader_prev_axis = -2", "input_cheat_index_plus_axis = +3",
            "input_fps_toggle_axis = +4", "input_shader_next_axis = -5",
        ))
        hotkeys = merged.translated_hotkey_bindings(base, mapping)
        self.assertEqual(hotkeys["input_enable_hotkey_btn"], "12")
        self.assertEqual(hotkeys["input_exit_emulator_btn"], "11")
        self.assertEqual(hotkeys["input_menu_toggle_btn"], "1")
        self.assertEqual(hotkeys["input_load_state_btn"], "3")
        self.assertEqual(hotkeys["input_save_state_btn"], "4")
        self.assertEqual(hotkeys["input_screenshot_btn"], "6")
        self.assertEqual(hotkeys["input_recording_toggle_btn"], "14")
        self.assertEqual(hotkeys["input_hold_fast_forward_btn"], "h0right")
        self.assertEqual(hotkeys["input_disk_next_axis"], "+0")
        self.assertEqual(hotkeys["input_disk_eject_toggle_axis"], "-1")
        self.assertEqual(hotkeys["input_cheat_index_plus_axis"], "+2")
        self.assertEqual(hotkeys["input_fps_toggle_axis"], "+3")
        self.assertEqual(hotkeys["input_shader_prev_axis"], "nul")
        self.assertEqual(hotkeys["input_shader_prev_btn"], "8")
        self.assertEqual(hotkeys["input_shader_next_axis"], "nul")
        self.assertEqual(hotkeys["input_shader_next_btn"], "9")
        updated = merged.merge_retroarch_config("video_smooth = true\n", 1, hotkeys)
        self.assertEqual(updated.count('input_enable_hotkey_btn = "12"'), 1)
        self.assertEqual(merged.merge_retroarch_config(updated, 1, hotkeys), updated)
        self.assertIn('input_exit_emulator_btn = "11"', updated)
        self.assertIn("# End VirtualGlove merged Player 1", updated)

    def test_batocera_uses_complete_hotkeys_on_the_merged_pad(self):
        saved = {"platform": "batocera", "mapping": self._mapping()}
        hotkeys = merged.platform_hotkey_bindings(saved, "")
        self.assertEqual(hotkeys["input_exit_emulator_btn"], "11")
        self.assertEqual(hotkeys["input_menu_toggle_btn"], "1")
        self.assertEqual(hotkeys["input_save_state_btn"], "4")
        self.assertEqual(hotkeys["input_load_state_btn"], "3")
        self.assertNotIn("input_reset_btn", hotkeys)

    def test_physical_device_is_grabbed_only_during_gameplay(self):
        device = merged.MergedGamepadDevice.__new__(merged.MergedGamepadDevice)
        device.descriptor = 17
        device.grabbed = False
        with patch.object(merged.fcntl, "ioctl") as ioctl:
            device._set_grab(True)
            device._set_grab(True)
            device._set_grab(False)
        self.assertEqual(ioctl.call_args_list, [
            call(17, merged.EVIOCGRAB, 1),
            call(17, merged.EVIOCGRAB, 0),
        ])

    def test_gameplay_transition_neutralizes_before_and_after_exclusive_ownership(self):
        device = merged.MergedGamepadDevice.__new__(merged.MergedGamepadDevice)
        device.descriptor = 17
        device.grabbed = False
        device.state = merged.MergeState()
        device.state.physical_buttons = {"a"}
        device.state.physical_axes["hat_x"] = 1
        published = []
        device.sink = type("Sink", (), {
            "write": lambda _self, buttons, axes: published.append(
                (set(buttons), dict(axes)))
        })()
        with patch.object(merged.fcntl, "ioctl") as ioctl:
            device._set_active(True)
            device._set_active(True)
            device.state.physical_buttons = {"b"}
            device.state.physical_axes["hat_x"] = -1
            device._set_active(False)
            device._set_active(False)
        self.assertEqual(ioctl.call_args_list, [
            call(17, merged.EVIOCGRAB, 1),
            call(17, merged.EVIOCGRAB, 0),
        ])
        self.assertFalse(device.state.active)
        self.assertEqual(device.state.physical_buttons, set())
        self.assertTrue(all(value == 0 for value in device.state.physical_axes.values()))
        neutral_axes = {name: 0 for name in merged.AXIS_CODES}
        self.assertEqual(published, [
            (set(), neutral_axes),
            (set(), neutral_axes),
        ])

    def test_batocera_assignment_clears_original_axis_bindings(self):
        hotkeys = merged.platform_hotkey_bindings(
            {"platform": "batocera", "mapping": self._mapping()}, "")
        updated = merged.merge_retroarch_config(
            'input_player1_l2_axis = "+5"\ninput_player1_up_axis = "-1"\n',
            2, hotkeys)
        self.assertEqual(updated.count('input_player1_l2_axis = "nul"'), 1)
        self.assertEqual(updated.count('input_player1_up_axis = "nul"'), 1)
        self.assertIn('input_exit_emulator_btn = "11"', updated)

    def test_uinput_device_has_fixed_gamepad_capabilities_and_emits_transitions(self):
        writes, ioctls = [], []
        with patch.object(merged.os, "open", return_value=17), \
                patch.object(merged.os, "write", side_effect=lambda _fd, data: writes.append(data)), \
                patch.object(merged.os, "close"), \
                patch.object(merged.fcntl, "ioctl",
                             side_effect=lambda *args: ioctls.append(args)):
            device = merged.UInputMergedGamepad()
            device.write({"a", "hotkey"}, {"hat_x": -1, "lx": 1234})
            device.close()
        self.assertIn((17, merged.UI_SET_EVBIT, merged.EV_KEY), ioctls)
        self.assertIn((17, merged.UI_SET_EVBIT, merged.EV_ABS), ioctls)
        self.assertIn((17, merged.UI_SET_KEYBIT, merged.BUTTON_CODES["hotkey"]), ioctls)
        self.assertIn((17, merged.UI_DEV_DESTROY), ioctls)
        events = []
        for payload in writes[1:]:
            if len(payload) == merged.UInputMergedGamepad.EVENT.size:
                events.append(struct.unpack("llHHi", payload))
        self.assertIn((0, 0, merged.EV_KEY, merged.BUTTON_CODES["a"], 1), events)
        self.assertIn((0, 0, merged.EV_KEY, merged.BUTTON_CODES["hotkey"], 1), events)
        self.assertIn((0, 0, merged.EV_ABS, merged.AXIS_CODES["hat_x"], -1), events)
        self.assertIn((0, 0, merged.EV_ABS, merged.AXIS_CODES["lx"], 1234), events)

    def test_saved_controller_record_rejects_unknown_format(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "controller.json"
            path.write_text(json.dumps({"format": 99, "mapping": []}))
            with self.assertRaisesRegex(ValueError, "unsupported"):
                merged.load_controller(path)

    def test_saved_controller_record_rejects_unbounded_mapping(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "controller.json"
            path.write_text(json.dumps({
                "format": 1, "platform": "recalbox", "name": "Pad",
                "mapping": [{"name": "shell", "type": "button", "code": 1, "value": 1}],
            }))
            with self.assertRaisesRegex(ValueError, "mapping"):
                merged.load_controller(path)

    def test_virtual_datagram_validation_is_bounded(self):
        valid = {"dpad": {"left": True}, "buttons": {"select": True},
                 "axes": {"x": -32767}}
        self.assertEqual(merged.virtual_state(valid), valid)
        self.assertIsNone(merged.virtual_state({"buttons": {"hotkey": True}}))
        self.assertIsNone(merged.virtual_state({"axes": {"x": 32768}}))
        self.assertIsNone(merged.virtual_state({"dpad": []}))

    def test_receiver_state_is_projected_onto_merged_gamepad_contract(self):
        state = {
            "dpad": {"left": True, "right": False},
            "buttons": {"a": True, "menu_guard": True, "closed_hand": True,
                        "index_point": False},
            "axes": {"x": -12000, "roll": 9000},
            "sequence": 42, "profile": "program_12", "detected": True,
        }
        payload = merged.merged_payload(state)
        self.assertEqual(payload, {
            "dpad": {"left": True, "right": False},
            "buttons": {"a": True},
            "axes": {"x": -12000, "roll": 9000},
        })
        self.assertEqual(merged.virtual_state(payload), payload)

    def _xml(self):
        temporary = tempfile.NamedTemporaryFile("w", delete=False)
        temporary.write(ES_INPUT)
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink)
        return Path(temporary.name)

    def _mapping(self):
        """Translate one realistic SDL/EmulationStation mapping for unit tests."""
        mapping = merged.parse_es_inputs(self._xml())[0]["mapping"]

        def populate(_descriptor, request, buffer, _mutate):
            if request == merged.JSIOCGAXES:
                buffer[0] = 4
            elif request == merged.JSIOCGBUTTONS:
                buffer[0] = 16
            elif request == merged.JSIOCGAXMAP:
                buffer[0] = 0
            elif request == merged.JSIOCGBTNMAP:
                for index, code in ((0, 304), (4, 310), (8, 314), (9, 315)):
                    struct.pack_into("H", buffer, index * 2, code)
            return 0

        with patch.object(merged.fcntl, "ioctl", side_effect=populate):
            return merged.translate_es_mapping(mapping, 17)


if __name__ == "__main__":
    unittest.main()
