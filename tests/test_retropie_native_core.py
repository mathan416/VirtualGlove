# Project: VirtualGlove
# File: tests/test_retropie_native_core.py
# Purpose: Verify the packaged multi-architecture RetroPie native cores.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-20 - Added packaged RetroPie architecture-matrix coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise RetroPie target selection, manifests, artifacts, and verification."""

import hashlib
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFY = runpy.run_path(str(ROOT / "scripts/verify-retropie-native-core.py"))


class RetroPieNativeCoreTests(unittest.TestCase):
    def test_installer_selects_retroarch_abi_and_replaces_atomically(self):
        script = (ROOT / "scripts/install-nestopia-powerglove.sh").read_text()
        self.assertIn('--runtime "$retroarch"', script)
        self.assertIn("cmp -s \"$core\" \"$installed\"", script)
        self.assertIn("/var/backups/virtualglove/nestopia-powerglove/", script)
        self.assertIn('mv -f "$temporary" "$installed"', script)
        self.assertIn("FCEUmm remains available", script)

    def test_complete_matrix_matches_every_packaged_artifact(self):
        manifest = ROOT / "native/retropie/manifest.json"
        data = json.loads(manifest.read_text())
        self.assertEqual(set(data["cores"]),
                         {"armv6", "armv7", "armv8_32", "aarch64", "x86_64"})
        patch_hash = hashlib.sha256(
            (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_bytes()
        ).hexdigest()
        for target, entry in data["cores"].items():
            self.assertEqual(entry["patch_sha256"], patch_hash)
            core = ROOT / "native/retropie" / entry["file"]
            verified = VERIFY["verify"](manifest, core, target)
            self.assertEqual(verified, entry)

    def test_cpu_resolution_distinguishes_armv7_and_32_bit_armv8(self):
        detect = VERIFY["detect_target"]
        self.assertEqual(detect("armv6l"), "armv6")
        self.assertEqual(detect("armv7l", "CPU architecture: 7\n"), "armv7")
        self.assertEqual(detect("armv7l", "CPU architecture : 8\n"), "armv8_32")
        self.assertEqual(detect("armv8l"), "armv8_32")
        self.assertEqual(detect("aarch64"), "aarch64")
        self.assertEqual(detect("x86_64"), "x86_64")
        with self.assertRaisesRegex(ValueError, "Unsupported RetroPie"):
            detect("mips64")

    def test_runtime_abi_overrides_a_64_bit_kernel(self):
        detect = VERIFY["detect_target"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arm32 = root / "retroarch-arm32"
            arm64 = root / "retroarch-arm64"
            x86_64 = root / "retroarch-x86_64"
            for path, elf_class, machine in ((arm32, 1, 40), (arm64, 2, 183),
                                             (x86_64, 2, 62)):
                header = bytearray(20)
                header[:6] = b"\x7fELF" + bytes((elf_class, 1))
                header[18:20] = machine.to_bytes(2, "little")
                path.write_bytes(header)
            cpuinfo = "CPU architecture: 8\n"
            self.assertEqual(detect("aarch64", cpuinfo, arm32), "armv8_32")
            self.assertEqual(detect("aarch64", cpuinfo, arm64), "aarch64")
            self.assertEqual(detect("aarch64", cpuinfo, x86_64), "x86_64")

    def test_tampered_core_is_rejected(self):
        source_root = ROOT / "native/retropie"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "retropie"
            shutil.copytree(source_root, copied)
            core = copied / "x86_64/nestopia_powerglove_libretro.so"
            core.write_bytes(core.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "does not match its manifest"):
                VERIFY["verify"](copied / "manifest.json", core, "x86_64")

    def test_x86_64_core_loads_and_identifies_itself(self):
        manifest = ROOT / "native/retropie/manifest.json"
        core = ROOT / "native/retropie/x86_64/nestopia_powerglove_libretro.so"
        try:
            VERIFY["verify"](manifest, core, "x86_64", load=True)
        except OSError as error:
            self.skipTest("Host cannot load the Linux x86-64 core: " + str(error))


if __name__ == "__main__":
    unittest.main()
