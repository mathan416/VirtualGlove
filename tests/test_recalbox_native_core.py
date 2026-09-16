# Project: VirtualGlove
# File: tests/test_recalbox_native_core.py
# Purpose: Verify isolated Recalbox native-core registration and selection.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added Recalbox native-core registration coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify isolated Recalbox native-core registration and selection."""

import json
import runpy
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE = runpy.run_path(
    str(ROOT / "scripts/configure-recalbox-super-glove-ball-core.py"))
VERIFY = runpy.run_path(
    str(ROOT / "scripts/verify-recalbox-native-core.py"))


SYSTEMS = """<?xml version="1.0" ?>
<systemList>
  <defaults command="launch" />
  <system uuid="nes-id" name="nes" fullname="Nintendo Entertainment System">
    <descriptor path="%ROOT%/nes" extensions=".nes" theme="nes" />
    <emulatorList><emulator name="libretro">
      <core name="nestopia" priority="1" extensions=".nes" />
      <core name="fceumm" priority="2" extensions=".nes" />
    </emulator></emulatorList>
  </system>
  <system uuid="snes-id" name="snes" fullname="SNES">
    <descriptor path="%ROOT%/snes" extensions=".sfc" theme="snes" />
    <emulatorList><emulator name="libretro"><core name="snes9x" /></emulator></emulatorList>
  </system>
</systemList>
"""


class RecalboxNativeCoreTests(unittest.TestCase):
    def test_systemlist_adds_one_low_priority_core_and_preserves_systems(self):
        updated = CONFIGURE["systemlist_text"](SYSTEMS)
        self.assertEqual(updated.count('name="nestopia_powerglove"'), 1)
        self.assertIn('name="nestopia"', updated)
        self.assertIn('name="fceumm"', updated)
        self.assertIn('name="snes"', updated)
        self.assertIn('priority="250"', updated)
        self.assertEqual(CONFIGURE["systemlist_text"](updated).count(
            'name="nestopia_powerglove"'), 1)

    def test_exact_rom_sidecar_preserves_unrelated_settings(self):
        current = "global.smooth=0\nnes.core=fceumm\nnes.ratio=4/3\n"
        native = CONFIGURE["selection_text"](current, "native")
        self.assertIn("global.smooth=0", native)
        self.assertIn("nes.ratio=4/3", native)
        self.assertEqual(native.count("nes.core="), 1)
        self.assertIn("nes.core=nestopia_powerglove", native)
        fallback = CONFIGURE["selection_text"](native, "fceumm")
        self.assertIn("nes.core=fceumm", fallback)
        self.assertNotIn("nestopia_powerglove", fallback)

    def test_auto_selection_matches_registry_and_preserves_existing_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roms = root / "roms"
            roms.mkdir()
            native = roms / "Super Glove Ball (USA).7z"
            native.write_bytes(b"rom")
            chosen = roms / "Super Glove Ball (USA).nes"
            chosen.write_bytes(b"rom")
            chosen_sidecar = chosen.with_name(chosen.name + ".recalbox.conf")
            chosen_sidecar.write_text("video.smooth=0\nnes.core=fceumm\n")
            unrelated = roms / "Super Mario Bros. (World).nes"
            unrelated.write_bytes(b"rom")
            registry = root / "games.json"
            registry.write_text(json.dumps({"games": {
                native.name: "super_glove_ball",
                chosen.name: {"profile": "super_glove_ball"},
                unrelated.name: "program_12",
            }}))

            selected, skipped = CONFIGURE["auto_select"](
                registry, roms, "native", True)

            self.assertEqual((selected, skipped), (1, 1))
            self.assertIn("nes.core=nestopia_powerglove",
                          native.with_name(native.name + ".recalbox.conf").read_text())
            self.assertEqual(chosen_sidecar.read_text(),
                             "video.smooth=0\nnes.core=fceumm\n")
            self.assertFalse(unrelated.with_name(
                unrelated.name + ".recalbox.conf").exists())

    def test_auto_selection_is_case_insensitive_and_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roms = root / "roms"
            roms.mkdir()
            actual = roms / "SUPER GLOVE BALL (USA).ZIP"
            actual.write_bytes(b"rom")
            link = roms / "Super Glove Ball (USA).7z"
            link.symlink_to(actual)
            registry = root / "games.json"
            registry.write_text(json.dumps({"games": {
                "Super Glove Ball (USA).zip": "super_glove_ball",
                "Super Glove Ball (USA).7z": "super_glove_ball",
            }}))
            selected, skipped = CONFIGURE["auto_select"](
                registry, roms, "native", True)
            self.assertEqual((selected, skipped), (1, 0))
            self.assertFalse(link.with_name(link.name + ".recalbox.conf").exists())

    def test_atomic_write_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real"
            target.write_text("safe")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic"):
                CONFIGURE["atomic_write"](link, "changed")
            self.assertEqual(target.read_text(), "safe")

    def test_build_uses_recalbox_recipe_and_exact_target(self):
        text = (ROOT / "scripts/build-recalbox-nestopia-powerglove.sh").read_text()
        self.assertIn('ARCH="$target"', text)
        self.assertLess(text.index("make clean"), text.index('make "recalbox-$target"_defconfig'))
        self.assertIn('LIBRETRO_NESTOPIA_OVERRIDE_SRCDIR="$source_dir"', text)
        self.assertIn("libretro-nestopia-dirclean libretro-nestopia", text)
        for target in ("rpizero2", "rpi3", "rpi4_64", "rpi5_64",
                       "rg353x", "odroidgo2", "x86_64"):
            self.assertIn(target, text)
        self.assertIn("libretro-nestopia-custom", text)
        self.assertIn('manifest="$destination/manifest.json"', text)
        self.assertIn("describe --tags --exact-match", text)

        patch = (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_text()
        self.assertIn("else ifeq ($(platform), rpi5_64)", patch)
        self.assertIn("PLATFORM_DEFINES += -mcpu=cortex-a76 -mtune=cortex-a76", patch)

        matrix = (ROOT / "scripts/build-recalbox-native-matrix.sh").read_text()
        for target in ("rpizero2", "rpi3", "rpi4_64", "rpi5_64",
                       "rg353x", "odroidgo2", "x86_64"):
            self.assertIn(target, matrix)

        workflow = (ROOT / ".github/workflows/recalbox-native-cores.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("gh release", workflow)
        for target in ("rpizero2", "rpi3", "rpi4_64", "rpi5_64",
                       "rg353x", "odroidgo2", "x86_64"):
            self.assertIn("- " + target, workflow)

    def test_all_recalbox_10_1_targets_match_manifest_and_elf(self):
        manifest = ROOT / "native/recalbox/manifest.json"
        expected = {
            "rpizero2": (32, "arm"),
            "rpi3": (32, "arm"),
            "rpi4_64": (64, "aarch64"),
            "rpi5_64": (64, "aarch64"),
            "rg353x": (64, "aarch64"),
            "odroidgo2": (64, "aarch64"),
            "x86_64": (64, "x86_64"),
        }
        for target, elf in expected.items():
            with self.subTest(target=target):
                core = (ROOT / "native/recalbox" / target / "10.1" /
                        "nestopia_powerglove_libretro.so")
                entry = VERIFY["verify"](manifest, core, target, "10.1")
                self.assertEqual(entry["recalbox_version"], "10.1")
                self.assertEqual((entry["elf_class"], entry["elf_machine"]), elf)
                self.assertEqual(entry["size"], core.stat().st_size)

    def test_manifest_rejects_unpackaged_version(self):
        with self.assertRaisesRegex(ValueError, "No packaged native core"):
            VERIFY["verify"](ROOT / "native/recalbox/manifest.json",
                             ROOT / "native/recalbox/rpizero2/10.1/nestopia_powerglove_libretro.so",
                             "rpizero2", "10.2")

    def test_manifest_rejects_target_elf_and_path_mismatches(self):
        source = json.loads((ROOT / "native/recalbox/manifest.json").read_text())
        entry = source["cores"]["rpizero2"]["10.1"]
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            wrong_elf = json.loads(json.dumps(source))
            wrong_elf["cores"]["rpizero2"]["10.1"]["elf_class"] = 64
            wrong_elf["cores"]["rpizero2"]["10.1"]["elf_machine"] = "aarch64"
            manifest.write_text(json.dumps(wrong_elf))
            with self.assertRaisesRegex(ValueError, "target and native-core ELF"):
                VERIFY["manifest_entry"](manifest, "rpizero2", "10.1")

            wrong_path = json.loads(json.dumps(source))
            wrong_path["cores"]["rpizero2"]["10.1"]["file"] = (
                "rpi3/10.1/nestopia_powerglove_libretro.so")
            manifest.write_text(json.dumps(wrong_path))
            with self.assertRaisesRegex(ValueError, "path does not match"):
                VERIFY["manifest_entry"](manifest, "rpizero2", "10.1")
        self.assertEqual(entry["elf_machine"], "arm")

    def test_installer_load_checks_before_atomic_replacement(self):
        text = (ROOT / "scripts/install-recalbox-nestopia-powerglove.sh").read_text()
        self.assertLess(text.index("verify-recalbox-native-core.py"),
                        text.index('mv "$temporary" "$target"'))
        self.assertIn('--version "$version" --load', text)
        self.assertIn("--mode native --apply", text)

    def test_boot_mount_automates_exact_rom_selection(self):
        text = (ROOT / "recalbox/virtualglove-core-mount").read_text()
        self.assertIn("--auto-select --apply", text)
        self.assertIn("--selection-only", text)
        self.assertIn('--registry "$APP/data/games.json"', text)
        self.assertIn("--rom-root /recalbox/share/roms/nes", text)
        self.assertIn("existing core choices are unchanged", text)


if __name__ == "__main__":
    unittest.main()
