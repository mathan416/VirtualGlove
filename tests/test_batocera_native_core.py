# Project: VirtualGlove
# File: tests/test_batocera_native_core.py
# Purpose: Verify isolated Batocera native-core selection and build integration.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added Batocera native-core isolation and selector coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify isolated Batocera native-core selection and build integration."""

import runpy
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE = runpy.run_path(
    str(ROOT / "scripts/configure-batocera-super-glove-ball-core.py"))


class BatoceraNativeCoreTests(unittest.TestCase):
    def test_exact_rom_selection_preserves_unrelated_configuration(self):
        rom = Path("/userdata/roms/nes/Super Glove Ball (USA).nes")
        current = (
            "global.videomode=default\n"
            'nes["Other.nes"].core=nestopia\n'
            'nes["Super Glove Ball (USA).nes"].core=fceumm\n'
        )
        native = CONFIGURE["configured_text"](current, rom, "native")
        self.assertIn("global.videomode=default", native)
        self.assertIn('nes["Other.nes"].core=nestopia', native)
        self.assertEqual(native.count("# VirtualGlove Super Glove Ball core"), 1)
        self.assertIn('nes["Super Glove Ball (USA).nes"].emulator=libretro', native)
        self.assertIn('nes["Super Glove Ball (USA).nes"].core=nestopia_powerglove', native)
        rolled_back = CONFIGURE["configured_text"](native, rom, "fceumm")
        self.assertNotIn("core=nestopia_powerglove", rolled_back)
        self.assertIn('nes["Super Glove Ball (USA).nes"].core=fceumm', rolled_back)

    def test_unsafe_filename_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot be represented"):
            CONFIGURE["configured_text"]("", Path('bad"name.nes'), "native")

    def test_atomic_write_refuses_symbolic_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real.conf"
            target.write_text("safe\n")
            link = root / "batocera.conf"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic"):
                CONFIGURE["atomic_write"](link, "changed\n")
            self.assertEqual(target.read_text(), "safe\n")

    def test_cross_build_uses_batocera_target_toolchain(self):
        text = (ROOT / "scripts/build-batocera-nestopia-powerglove.sh").read_text()
        self.assertIn('"$target-pkg" PKG=libretro-nestopia', text)
        self.assertIn('output/$target/host/bin', text)
        self.assertIn("VIRTUALGLOVE_LIBRETRO_PLATFORM", text)
        self.assertIn("nestopia_powerglove_libretro.so", text)

    def test_target_installer_load_checks_before_atomic_replacement(self):
        text = (ROOT / "scripts/install-batocera-nestopia-powerglove.sh").read_text()
        load = text.index("ctypes.CDLL")
        replace = text.index('mv "$temporary" "$target"')
        self.assertLess(load, replace)
        self.assertIn("virtualglove-core-mount\" restart", text)
        self.assertIn("--mode native --apply", text)


if __name__ == "__main__":
    unittest.main()
