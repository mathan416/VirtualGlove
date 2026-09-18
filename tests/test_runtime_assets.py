# Project: VirtualGlove
# File: tests/test_runtime_assets.py
# Purpose: Verify model download caching, checksum enforcement, and atomic installation behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-03 - Added with standardized source documentation.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify model download caching, checksum enforcement, and atomic installation behavior."""

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from virtualglove.runtime_assets import ensure_hand_landmarker_model


class RuntimeAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_downloads_and_caches_verified_model(self) -> None:
        content = b"verified model content"
        expected = hashlib.sha256(content).hexdigest()
        calls = []

        def open_model(url, timeout):
            calls.append((url, timeout))
            return io.BytesIO(content)

        path = ensure_hand_landmarker_model(
            self.data, url="https://example.test/model", expected_sha256=expected, bundled_path=self.data / "absent.task", opener=open_model
        )
        self.assertEqual(path.read_bytes(), content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(calls, [("https://example.test/model", 60)])

        def should_not_download(_url, _timeout):
            raise AssertionError("verified cached model should be reused")

        self.assertEqual(
            ensure_hand_landmarker_model(
                self.data, expected_sha256=expected, opener=should_not_download
            ),
            path,
        )

    def test_checksum_failure_does_not_install_download(self) -> None:
        def open_bad_model(_url, timeout):
            self.assertEqual(timeout, 60)
            return io.BytesIO(b"tampered")

        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            ensure_hand_landmarker_model(
                self.data, expected_sha256=hashlib.sha256(b"expected").hexdigest(),
                bundled_path=self.data / "absent.task", opener=open_bad_model,
            )
        self.assertFalse((self.data / "models" / "hand_landmarker.task").exists())
        self.assertEqual(list((self.data / "models").glob("*.download")), [])

    def test_bundle_installs_offline_and_repairs_bad_cache(self) -> None:
        content = b"verified bundled model"
        bundle = self.data / "bundle.task"
        bundle.write_bytes(content)
        cache = self.data / "models" / "hand_landmarker.task"
        cache.parent.mkdir()
        cache.write_bytes(b"damaged cache")
        def no_network(*args, **kwargs):
            raise AssertionError("offline installation attempted network access")
        path = ensure_hand_landmarker_model(
            self.data, expected_sha256=hashlib.sha256(content).hexdigest(),
            bundled_path=bundle, opener=no_network,
        )
        self.assertEqual(path.read_bytes(), content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_bad_bundle_is_rejected_without_download(self) -> None:
        bundle = self.data / "bundle.task"
        bundle.write_bytes(b"damaged bundle")
        def no_network(*args, **kwargs):
            raise AssertionError("bad bundle must not be silently replaced")
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            ensure_hand_landmarker_model(self.data, bundled_path=bundle, opener=no_network)
        self.assertFalse((self.data / "models" / "hand_landmarker.task").exists())
        self.assertEqual(list((self.data / "models").glob("*.download")), [])


if __name__ == "__main__":
    unittest.main()
