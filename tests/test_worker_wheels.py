# Project: VirtualGlove
# File: tests/test_worker_wheels.py
# Purpose: Verify the locked UNO Q vision-worker wheels are packaged for offline worker starts.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-11-24 - Added with the bundled worker wheels.
# Full history: docs/CHANGELOG.md and Git history.

import hashlib
import importlib.util
import runpy
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WHEELS = runpy.run_path(str(ROOT / "scripts/worker-wheels.py"))
MEDIAPIPE = "mediapipe-0.10.35+powerglove.cpu1-cp312-cp312-linux_aarch64.whl"


def lock_text(files: dict[str, bytes]) -> str:
    lines = [WHEELS["HEADER"]]
    for filename, data in files.items():
        name, version = filename.split("-")[:2]
        lines.append(f"# wheel: {filename}\n{name}=={version} "
                     f"--hash=sha256:{hashlib.sha256(data).hexdigest()}\n")
    return "".join(lines)


class LockTests(unittest.TestCase):
    def test_lock_covers_every_mediapipe_dependency_with_one_uno_q_wheel(self):
        entries = WHEELS["entries"]()
        names = {entry["name"].lower().replace("_", "-") for entry in entries}
        with zipfile.ZipFile(ROOT / "python/worker-wheels" / MEDIAPIPE) as wheel:
            metadata = wheel.read("mediapipe-0.10.35+powerglove.cpu1.dist-info/METADATA").decode()
        required = {line.split(":", 1)[1].strip().split()[0].split(">")[0].split("<")[0]
                    .split("=")[0].lower() for line in metadata.splitlines()
                    if line.startswith("Requires-Dist:") and "extra ==" not in line}
        self.assertLessEqual(required, names)
        self.assertEqual(len(names), len(entries))
        for entry in entries:
            with self.subTest(wheel=entry["filename"]):
                self.assertIsNotNone(WHEELS["wheel_score"](entry["filename"]))
                stem = entry["filename"].split("-")
                self.assertEqual(stem[0].lower(), entry["name"].lower().replace("-", "_"))
                self.assertEqual(stem[1], entry["version"])
        # The validated MediaPipe build needs these exact versions.
        versions = {entry["name"]: entry["version"] for entry in entries}
        self.assertEqual(versions["numpy"], "1.26.4")
        self.assertEqual(versions["opencv-contrib-python-headless"], "4.11.0.86")

    def test_wheel_selection_matches_the_uno_q_worker(self):
        score = WHEELS["wheel_score"]
        accepted = ["numpy-1.26.4-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
                    "protobuf-4.25.9-cp37-abi3-manylinux2014_aarch64.whl",
                    "attrs-26.1.0-py3-none-any.whl",
                    "six-1.0-py2.py3-none-any.whl"]
        rejected = ["numpy-1.26.4-cp312-cp312-manylinux_2_17_x86_64.whl",
                    "numpy-1.26.4-cp313-cp313-manylinux_2_17_aarch64.whl",
                    "numpy-1.26.4-cp312-cp312-musllinux_1_1_aarch64.whl",
                    "numpy-1.26.4-cp312-cp312-manylinux_2_99_aarch64.whl",
                    "numpy-1.26.4-cp312-cp312-macosx_14_0_arm64.whl",
                    "future-1.0-cp313-abi3-manylinux_2_28_aarch64.whl",
                    "not-a-wheel.tar.gz"]
        for name in accepted:
            self.assertIsNotNone(score(name), name)
        for name in rejected:
            self.assertIsNone(score(name), name)
        # Prefer a CPython 3.12 build over a pure-Python one for the same release.
        self.assertGreater(score("x-1-cp312-cp312-manylinux_2_28_aarch64.whl"),
                           score("x-1-py3-none-any.whl"))


class FolderTests(unittest.TestCase):
    def test_problems_name_missing_unexpected_and_altered_wheels(self):
        files = {"a-1-py3-none-any.whl": b"a", "b-2-py3-none-any.whl": b"b"}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "wheels"
            folder.mkdir()
            lock = Path(directory) / "lock.txt"
            lock.write_text(lock_text(files))
            (folder / "a-1-py3-none-any.whl").write_bytes(b"a")
            (folder / "c-3-py3-none-any.whl").write_bytes(b"c")
            self.assertEqual(WHEELS["problems"](folder, lock),
                             ["missing b-2-py3-none-any.whl", "unexpected c-3-py3-none-any.whl"])
            (folder / "c-3-py3-none-any.whl").unlink()
            (folder / "b-2-py3-none-any.whl").write_bytes(b"tampered")
            self.assertEqual(WHEELS["problems"](folder, lock),
                             ["checksum mismatch b-2-py3-none-any.whl"])
            (folder / "b-2-py3-none-any.whl").write_bytes(b"b")
            self.assertEqual(WHEELS["problems"](folder, lock), [])

    def test_payload_carries_only_a_verified_wheel_set(self):
        payload = runpy.run_path(str(ROOT / "scripts/application-payload.py"))
        files = {"a-1-py3-none-any.whl": b"a"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            (root / "python").mkdir(parents=True)
            (root / "python/worker-requirements.txt").write_text(lock_text(files))
            (root / "scripts").mkdir()
            (root / "scripts/worker-wheels.py").write_text(
                (ROOT / "scripts/worker-wheels.py").read_text())
            (root / "app.yaml").write_text("name: test")
            wheels = root / "output/worker-wheels"
            wheels.mkdir(parents=True)
            selected = {"selected_files": lambda *_args, **_kwargs: ["app.yaml"]}
            with patch.object(payload["subprocess"], "run"), \
                    patch.dict(payload["stage"].__globals__, selected):
                with self.assertRaisesRegex(ValueError, "worker-wheels.py fetch"):
                    payload["stage"](root, Path(directory) / "missing", worker_wheels=True)
                (wheels / "a-1-py3-none-any.whl").write_bytes(b"a")
                destination = Path(directory) / "destination"
                payload["stage"](root, destination, worker_wheels=True)
                plain = Path(directory) / "plain"
                payload["stage"](root, plain)
            self.assertEqual((destination / "python/worker-wheels/a-1-py3-none-any.whl").read_bytes(), b"a")
            self.assertFalse((plain / "python/worker-wheels").exists())


class PackageTests(unittest.TestCase):
    def verifier(self):
        spec = importlib.util.spec_from_file_location(
            "package_verifier_worker_wheels", ROOT / "scripts/verify-app-lab-package.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def errors(self, files: dict[str, bytes], lock: str | None) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "package.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("VirtualGlove/python/worker-wheels/" + MEDIAPIPE, b"m")
                if lock is not None:
                    output.writestr("VirtualGlove/python/worker-requirements.txt", lock)
                for name, data in files.items():
                    output.writestr("VirtualGlove/python/worker-wheels/" + name, data)
            return [error for error in self.verifier().archive_errors(archive)
                    if "worker wheel" in error or "MediaPipe" in error]

    def test_package_requires_exactly_the_locked_wheels(self):
        locked = {"a-1-py3-none-any.whl": b"a", "b-2-py3-none-any.whl": b"b"}
        lock = lock_text(locked)
        self.assertEqual(self.errors(locked, lock), [])
        self.assertEqual(self.errors({"a-1-py3-none-any.whl": b"a"}, lock),
                         ["locked worker wheel missing from package: b-2-py3-none-any.whl"])
        self.assertEqual(self.errors(dict(locked, **{"c-3-py3-none-any.whl": b"c"}), lock),
                         ["unlocked worker wheel in package: c-3-py3-none-any.whl"])
        self.assertEqual(self.errors(dict(locked, **{"b-2-py3-none-any.whl": b"x"}), lock),
                         ["worker wheel checksum mismatch: b-2-py3-none-any.whl"])
        self.assertIn("worker wheel lock is missing or empty", self.errors(locked, None))
        extra = self.errors(dict(locked, **{"mediapipe-0.10.36-cp312-cp312-linux_aarch64.whl": b"n"}), lock)
        self.assertIn("expected validated UNO Q MediaPipe 0.10.35 wheel only", extra)

    def test_release_and_development_builds_bundle_the_wheels(self):
        for script in ("scripts/build-app-lab-package.sh", "scripts/deploy-uno-q-wifi.sh"):
            with self.subTest(script=script):
                text = (ROOT / script).read_text()
                fetch = text.index('worker-wheels.py" fetch')
                stage = text.index("application-payload.py")
                self.assertLess(fetch, stage)
                self.assertIn("--worker-wheels", text[stage:stage + 300])
        self.assertIn("/output/worker-wheels/", (ROOT / ".gitignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
