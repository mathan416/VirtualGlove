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
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE = runpy.run_path(
    str(ROOT / "scripts/configure-batocera-super-glove-ball-core.py"))
VERIFY = runpy.run_path(str(ROOT / "scripts/verify-batocera-native-core.py"))


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

    def test_auto_selection_preserves_explicit_rom_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roms = root / "roms"
            roms.mkdir()
            first = roms / "Super Glove Ball (USA).nes"
            second = roms / "Super Glove Ball (USA) (Rev A).nes"
            first.touch()
            second.touch()
            registry = root / "games.json"
            registry.write_text(json.dumps({"games": {
                first.name: "super_glove_ball", second.name: "super_glove_ball"
            }}))
            config = root / "batocera.conf"
            config.write_text('nes["Super Glove Ball (USA) (Rev A).nes"].core=fceumm\n')
            selected, skipped = CONFIGURE["auto_select"](
                config, registry, roms, "native", True)
            text = config.read_text()
        self.assertEqual((selected, skipped), (1, 1))
        self.assertIn('nes["Super Glove Ball (USA).nes"].core=nestopia_powerglove', text)
        self.assertIn('nes["Super Glove Ball (USA) (Rev A).nes"].core=fceumm', text)

    def test_matrix_manifest_resolves_newer_batocera_to_verified_target(self):
        manifest = ROOT / "native/batocera/manifest.json"
        entry = VERIFY["manifest_entry"](manifest, "x86_64", "44")
        self.assertEqual(entry["batocera_version"], "43.1")
        verified = VERIFY["verify"](
            manifest,
            ROOT / "native/batocera/x86_64/43.1/nestopia_powerglove_libretro.so",
            "x86_64", "44")
        self.assertEqual(verified["elf_machine"], "x86_64")

    def test_every_supported_target_has_a_complete_matrix_entry(self):
        manifest = ROOT / "native/batocera/manifest.json"
        for target in VERIFY["TARGET_ELF"]:
            with self.subTest(target=target):
                entry = VERIFY["manifest_entry"](manifest, target, "43.1")
                self.assertIsNotNone(entry)
                self.assertTrue((manifest.parent / entry["file"]).is_file())
                self.assertTrue((manifest.parent / entry["source_file"]).is_file())

    def test_cross_build_uses_batocera_target_toolchain(self):
        text = (ROOT / "scripts/build-batocera-nestopia-powerglove.sh").read_text()
        self.assertIn("virtualglove/batocera-linux-build:43.1", text)
        self.assertIn('docker build -t "$image" - < "$batocera/Dockerfile"', text)
        self.assertIn('destination=$(CDPATH= cd -- "$destination" && pwd)', text)
        self.assertIn("-C /build/buildroot toolchain", text)
        self.assertIn('CC="$prefix-gcc" CXX="$cxx"', text)
        self.assertIn("platform='\"$platform\"'", text)
        self.assertIn("BR2_DL_DIR=/downloads", text)
        self.assertIn("Batocera core ELF identity does not match its target", text)
        self.assertIn("nestopia_powerglove_libretro.so", text)

    def test_matrix_builder_resumes_verified_targets(self):
        text = (ROOT / "scripts/build-batocera-native-matrix.sh").read_text()
        self.assertIn("verify-batocera-native-core.py", text)
        self.assertIn("SKIP  Verified Batocera", text)
        for target in VERIFY["TARGET_ELF"]:
            self.assertIn(target, text)

    def test_target_installer_load_checks_before_atomic_replacement(self):
        text = (ROOT / "scripts/install-batocera-nestopia-powerglove.sh").read_text()
        load = text.index("ctypes.CDLL")
        replace = text.index('mv "$temporary" "$target"')
        self.assertLess(load, replace)
        self.assertIn("virtualglove-core-mount\" restart", text)
        self.assertIn("--mode native --apply", text)


if __name__ == "__main__":
    unittest.main()
