# Project: VirtualGlove
# File: tests/test_sgb_core_setup.py
# Purpose: Verify reversible per-ROM native/FCEUmm selection.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added reversible Super Glove Ball core-selection coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify reversible per-ROM native and FCEUmm selection."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sgb_core", ROOT / "scripts/configure-super-glove-ball-core.py")
sgb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sgb)


class SuperGloveBallCoreSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.prefix = Path(self.temporary.name) / "opt/retropie"
        self.rom = Path(self.temporary.name) / "roms/Super Glove Ball (USA).nes"
        self.rom.parent.mkdir(parents=True)
        self.rom.write_bytes(b"test-only")
        fallback = self.prefix / "libretrocores/lr-fceumm/fceumm_libretro.so"
        fallback.parent.mkdir(parents=True)
        fallback.write_bytes(b"core")
        system = self.prefix / "configs/nes/emulators.cfg"
        system.parent.mkdir(parents=True)
        system.write_text('default = "lr-fceumm"\nlr-fceumm = "/retroarch -L ' + str(fallback) + ' --config base.cfg %ROM%"\n')

    def tearDown(self):
        self.temporary.cleanup()

    def test_native_selection_is_isolated_and_reversible(self):
        native = self.prefix / "libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so"
        native.parent.mkdir(parents=True)
        native.write_bytes(b"native")
        system_path, system_text, games_path, games_text = sgb.plan(self.prefix, self.rom, "native")
        self.assertIn("VIRTUALGLOVE_NATIVE_STATE=/run/virtualglove/native-state", system_text)
        self.assertIn("--device=1:517", system_text)
        self.assertIn(str(native), system_text)
        option_path, option_text = sgb.native_options(self.prefix)
        self.assertIn("--appendconfig " + str(option_path), system_text)
        self.assertEqual(option_text, 'input_libretro_device_p1 = "517"\nvideo_threaded = "false"\n')
        self.assertIn(sgb.game_key(self.rom) + ' = "lr-nestopia-powerglove"', games_text)
        sgb.write_file(system_path, system_text)
        sgb.write_file(games_path, games_text)
        _, preserved_system, _, fallback_games = sgb.plan(self.prefix, self.rom, "fceumm")
        self.assertEqual(preserved_system, system_text)
        self.assertIn(sgb.game_key(self.rom) + ' = "lr-fceumm"', fallback_games)
        self.assertNotIn("powerglove-native.cfg", sgb.settings(self.prefix / "configs/nes/emulators.cfg")["lr-fceumm"])

    def test_native_requires_both_native_core_and_fallback(self):
        with self.assertRaisesRegex(ValueError, "Build and install"):
            sgb.plan(self.prefix, self.rom, "native")

    def test_registration_adds_menu_choice_without_selecting_rom(self):
        native = self.prefix / "libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so"
        native.parent.mkdir(parents=True)
        native.write_bytes(b"native")
        system_path, system_text, option_path, option_text = sgb.native_registration(self.prefix)
        self.assertIn('lr-fceumm = ', system_text)
        self.assertIn('lr-nestopia-powerglove = ', system_text)
        self.assertNotIn(sgb.game_key(self.rom), system_text)
        sgb.register_native(self.prefix)
        self.assertEqual(system_path.read_text(), system_text)
        self.assertEqual(option_path.read_text(), option_text)


if __name__ == "__main__":
    unittest.main()
