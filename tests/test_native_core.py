# Project: VirtualGlove
# File: tests/test_native_core.py
# Purpose: Keep the experimental Nestopia core isolated and evidence-gated.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Aligned evidence assertions with the confirmed completed native game.
#   2026-09-05 - Required native depth, fist, and index-point packet mapping.
#   2026-09-05 - Distinguished confirmed recognition from unmapped native fields.
#   2026-09-04 - Required installed records to identify the exact local patch.
#   2026-09-04 - Added isolation, protocol evidence, and distribution checks.
# Full history: docs/CHANGELOG.md and Git history.

"""Check the reproducible native research spike without building over the network."""

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NativeCoreTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ compiler required for calibration core")
    def test_calibration_dot_core_is_standalone_and_buildable(self):
        source = ROOT / "native/powerglove-dot/powerglove_dot.cpp"
        text = source.read_text()
        for evidence in (
            'std::memcmp(data, "PGV1", 4)', "first_guard != last_guard",
            "now - arrived > STALE_NS", "PROFILE_SUPER_GLOVE_BALL",
            "RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME", "4.0f / 3.0f",
        ):
            self.assertIn(evidence, text)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "powerglove_dot_libretro.so"
            subprocess.run(["c++", "-std=c++11", "-O2", "-fPIC", "-shared",
                            str(source), "-o", str(output)], check=True)
            self.assertGreater(output.stat().st_size, 0)

    def test_build_is_pinned_separate_and_uses_local_patch(self):
        script = (ROOT / "scripts/build-nestopia-powerglove.sh").read_text()
        self.assertIn("5a1cd378cb46ca9ccc2dd6f8b2b6a79ab986052e", script)
        self.assertIn("nestopia_powerglove_libretro", script)
        self.assertIn("native/nestopia-powerglove/nestopia-powerglove.patch", script)
        self.assertNotIn("/opt/retropie/libretrocores", script)
        self.assertNotIn("reset --hard", script)
        self.assertIn('cat-file -e "$revision^{commit}"', script)
        self.assertIn('make -C "$source_dir/libretro" -j"${JOBS:-2}"', script)
        self.assertIn("VIRTUALGLOVE_LIBRETRO_PLATFORM", script)
        self.assertIn("The patch changed Nestopia's original copyright/license header", script)
        self.assertIn("NstInpPowerGlove.cpp", script)

    def test_patch_has_coherent_stale_safe_xy_bridge_and_trace(self):
        patch = (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_text()
        for evidence in (
            'memcmp(out->magic, "PGV1", 4)',
            "out->guard_begin != out->guard_end",
            "now - out->arrived_ns <= 250000000ULL",
            "out->profile != 1",
            "glove.x =",
            "glove.y =",
            "glove.x = 128",
            "glove.y = 128",
            "Nestopia's 128-glove.y packet",
            "host value directly compensates",
            "VirtualGloveNativeEnabled() ? 10U : 12U",
            "glove.distance = 0",
            "glove.wrist = 0",
            "GESTURE_OPEN",
            "sample.z * 127 / 32767",
            "sample.buttons & (1 << 6)",
            "GESTURE_FIST",
            "sample.buttons & (1 << 7)",
            "GESTURE_FINGER",
            "buffer[3] = static_cast<byte>(glove.distance)",
            "VIRTUALGLOVE_TRACE",
            "PGV read bit=",
            "PGV config/write bit=",
            "packet boundary falling-strobe",
            "packet clock=%lu bytes=",
            'library_name     = "Nestopia PowerGlove"',
            "if (port == 0)",
            "Api::Input::POWERGLOVE",
            "return true;",
        ):
            self.assertIn(evidence, patch)

    def test_compatibility_record_separates_confirmed_recognition_and_native_mapping(self):
        record = (ROOT / "docs/super-glove-ball-native.md").read_text()
        self.assertIn("NESdev material is a source of testable hypotheses", record)
        self.assertIn("Detection signature, packet length, boundaries, and bit order | Confirmed", record)
        self.assertIn("Native Z encoding | Confirmed headlessly and in live gameplay", record)
        self.assertIn(
            "Native open, fist, and index-point encoding | Confirmed headlessly and in live gameplay",
            record,
        )
        self.assertIn(
            "Native roll byte and unobserved button codes | Neutral; no confirmed game action is missing",
            record,
        )
        self.assertIn("## Build and install the native core", record)
        self.assertIn(
            "Shared five-finger recognition determines compound poses before transmission",
            record,
        )
        self.assertIn("explicit FCEUmm", record)

    def test_trace_runner_records_digest_phases_and_safe_neutral_cases(self):
        runner = (ROOT / "scripts/run-nestopia-powerglove-trace.py").read_text()
        for evidence in (
            "rom_sha256", "trace_evidence", '"tracking_lost"',
            '"uncalibrated"', '"stale"', '"fist"', '"index_point"',
            '"power_punch"', "packet_values",
        ):
            self.assertIn(evidence, runner)

    def test_distribution_keeps_gpl_notice_with_installed_core(self):
        installer = (ROOT / "scripts/install-nestopia-powerglove.sh").read_text()
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
        self.assertIn('nestopia-powerglove-source.tar.gz', installer)
        self.assertIn('tar -xzf "$source_archive"', installer)
        self.assertIn('target/COPYING', installer)
        self.assertIn('VIRTUALGLOVE-NOTICES.md', installer)
        self.assertIn("GNU General Public License, version 2", notice)
        self.assertIn(
            "each bundled binary is accompanied by its exact complete corresponding source",
            notice,
        )
        self.assertIn("Recalbox 10.1 `rpizero2`", notice)
        patch_digest = hashlib.sha256(
            (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_bytes()
        ).hexdigest()
        self.assertIn(patch_digest, notice)
        self.assertIn("Martin Freij", notice)
        self.assertIn("leaves it", notice)
        self.assertIn("byte-for-byte unchanged", notice)
        self.assertIn("camera-to-Nestopia Y orientation", notice)

    def test_patch_does_not_remove_upstream_attribution(self):
        patch = (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_text()
        removed = [line[1:] for line in patch.splitlines()
                   if line.startswith("-") and not line.startswith("---")]
        protected_words = ("copyright", "license", "nestopia is free software", "martin freij")
        self.assertFalse(any(word in line.lower()
                             for line in removed for word in protected_words))


if __name__ == "__main__":
    unittest.main()
