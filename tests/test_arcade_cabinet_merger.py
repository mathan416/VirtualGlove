#!/usr/bin/env python3
# Project: VirtualGlove
# File: tests/test_arcade_cabinet_merger.py
# Purpose: Preserve the proven optional RetroPie cabinet-merger semantics.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added regression coverage for the recovered cabinet integration.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the optional I-PAC, 8BitDo, and VirtualGlove cabinet merger."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "retropie/arcade-cabinet-merger/arcade-gamepad-merger"
PROPOSAL_SOURCE = ROOT / "retropie/arcade-cabinet-merger/propose-controller-router.py"


class FakeCodes:
    EV_KEY = 1
    EV_ABS = 3
    BUS_USB = 3
    BTN_SOUTH = 304
    BTN_EAST = 305
    BTN_C = 306
    BTN_NORTH = 307
    BTN_WEST = 308
    BTN_Z = 309
    BTN_TL = 310
    BTN_TR = 311
    BTN_TL2 = 312
    BTN_TR2 = 313
    BTN_SELECT = 314
    BTN_START = 315
    BTN_MODE = 316
    BTN_THUMBL = 317
    BTN_THUMBR = 318
    BTN_DPAD_UP = 544
    BTN_DPAD_DOWN = 545
    BTN_DPAD_LEFT = 546
    BTN_DPAD_RIGHT = 547
    ABS_X = 0
    ABS_Y = 1
    ABS_Z = 2
    ABS_RX = 3
    ABS_RY = 4
    ABS_RZ = 5
    ABS_GAS = 9
    ABS_BRAKE = 10
    ABS_HAT0X = 16
    ABS_HAT0Y = 17


class FakeUInput:
    def __init__(self, _capabilities, **_metadata):
        self.device = types.SimpleNamespace(path="/dev/input/fake")
        self.events = []

    def write(self, event_type, code, value):
        self.events.append((event_type, code, value))

    def syn(self):
        self.events.append(("syn",))

    def close(self):
        return None


def load_merger():
    """Load the extensionless installed program with a bounded evdev double."""
    evdev = types.ModuleType("evdev")
    evdev.AbsInfo = lambda *values: values
    evdev.InputDevice = object
    evdev.UInput = FakeUInput
    evdev.ecodes = FakeCodes
    evdev.list_devices = lambda: []
    loader = importlib.machinery.SourceFileLoader("arcade_gamepad_merger", str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"evdev": evdev}):
        loader.exec_module(module)
    return module


def load_proposal():
    """Load the cabinet proposal helper whose installed filename contains a hyphen."""
    loader = importlib.machinery.SourceFileLoader("cabinet_router_proposal", str(PROPOSAL_SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ArcadeCabinetMergerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.merger = load_merger()
        cls.proposal = load_proposal()

    def test_outputs_preserve_the_proven_two_player_identity(self):
        self.assertEqual(
            self.merger.OUTPUT_NAMES,
            ("Arcade Merged Player 1", "Arcade Merged Player 2"),
        )

    def test_button_remains_held_until_every_source_releases_it(self):
        output = self.merger.PlayerOutput(0)
        code = self.merger.ecodes.BTN_SOUTH
        self.assertTrue(output.set_key("ipac-p1", code, 1))
        self.assertFalse(output.set_key("virtualglove-p1", code, 1))
        self.assertFalse(output.set_key("ipac-p1", code, 0))
        self.assertTrue(output.set_key("virtualglove-p1", code, 0))
        self.assertEqual(
            [event for event in output.device.events if event[0] == self.merger.ecodes.EV_KEY],
            [(self.merger.ecodes.EV_KEY, code, 1),
             (self.merger.ecodes.EV_KEY, code, 0)],
        )

    def test_releasing_a_source_restores_another_active_axis(self):
        output = self.merger.PlayerOutput(0)
        axis = self.merger.ecodes.ABS_HAT0X
        with patch.object(self.merger.time, "monotonic", side_effect=(1.0, 2.0)):
            output.set_axis("ipac-p1", axis, -1)
            output.set_axis("virtualglove-p1", axis, 1)
        output.release_source("virtualglove-p1")
        self.assertEqual(output.output_axes[axis], -1)

    def test_virtualglove_cannot_emit_the_hotkey_enable_button(self):
        self.assertNotIn(self.merger.ecodes.BTN_MODE,
                         self.merger.VIRTUALGLOVE_KEYS.values())
        self.assertEqual(
            self.merger.VIRTUALGLOVE_KEYS[self.merger.ecodes.BTN_SELECT],
            self.merger.ecodes.BTN_SELECT,
        )

    def test_recovered_retroarch_profiles_match_output_identities_and_hotkey(self):
        profile_root = ROOT / "retropie/arcade-cabinet-merger/retroarch"
        for player, product in ((1, "41216"), (2, "41217")):
            text = (profile_root / f"Arcade Merged Player {player}.cfg").read_text()
            self.assertIn(f'input_device = "Arcade Merged Player {player}"', text)
            self.assertIn('input_vendor_id = "4617"', text)
            self.assertIn(f'input_product_id = "{product}"', text)
            self.assertIn('input_enable_hotkey_btn = "12"', text)
            self.assertIn('input_select_btn = "10"', text)

    def test_cabinet_router_migration_is_preflight_gated_and_reversible(self):
        text = (ROOT / "retropie/arcade-cabinet-merger/"
                       "cabinet-controller-router-migration.py").read_text()
        self.assertIn('choices=("check", "apply", "rollback")', text)
        self.assertIn("No input was observed from:", text)
        self.assertIn('"proposed physical source during validation."', text)
        self.assertIn("while assigned - set(activity)", text)
        self.assertIn("min(1000, remaining_ms)", text)
        self.assertIn("ControllerRouterDevice(", text)
        self.assertIn('"fceumm_config": _saved_file(FCEUMM_CONFIG)', text)
        self.assertIn('"nes_config": _saved_file(NES_CONFIG)', text)
        self.assertIn('"joystick_selection": _saved_file(JOYSTICK_SELECTION)', text)
        self.assertIn('_restore(FCEUMM_CONFIG, state.get("fceumm_config")', text)
        self.assertIn('_restore(NES_CONFIG, state.get("nes_config")', text)
        self.assertIn('_restore(JOYSTICK_SELECTION, state.get("joystick_selection")', text)
        self.assertIn('if "Arcade Merged Player" in selection:', text)
        self.assertIn('_merged_joystick_selection(proposal)', text)
        self.assertIn('os.chown(str(path), saved["uid"], saved["gid"])', text)
        self.assertIn('"disable", "--now", OLD_SERVICE', text)
        self.assertIn("deadline = time.monotonic() + 5.0", text)
        self.assertIn("if len(indexes) == len(players)", text)

    def test_cabinet_proposal_preserves_known_ipac_player1_hotkey(self):
        source = {"mapping": [{"name": "a", "type": "button", "code": 0,
                                "value": 1}]}
        updated = self.proposal.with_cabinet_hotkey(source)
        self.assertEqual(updated["mapping"][-1], {
            "name": "hotkey", "type": "button", "code": 298,
            "value": 1, "evdev_code": 298,
        })
        self.assertEqual(source["mapping"], [
            {"name": "a", "type": "button", "code": 0, "value": 1}
        ])


if __name__ == "__main__":
    unittest.main()
