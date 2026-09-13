#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-matrix-firmware.py
# Purpose: Build a pinned UNO Q Matrix image for release packages.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Added reproducible, checksum-described precompiled firmware output.
# Full history: docs/CHANGELOG.md and Git history.

"""Build the pinned Matrix sketch and preserve only the files needed to flash it."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/matrix-firmware"
CORE = "arduino:zephyr@1.0.0"
FQBN = "arduino:zephyr:unoq"
COMPILE_FQBN = FQBN + ":wait_linux_boot=app"
LIBRARIES = (
    "Arduino_RouterBridge@0.4.3", "Arduino_RPClite@0.3.0",
    "ArxContainer@0.7.0", "ArxTypeTraits@0.3.2",
    "DebugLog@0.8.4", "MsgPack@0.4.2",
)


def digest(path):
    """Hash one artifact without loading a multi-megabyte loader at once."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def command(*args):
    """Run a build command with no shell interpretation."""
    subprocess.run(list(map(str, args)), cwd=str(ROOT), check=True)


def package_directory():
    """Return Arduino CLI's configured package data directory."""
    result = subprocess.check_output(
        ["arduino-cli", "config", "get", "directories.data"], text=True).strip()
    if not result:
        raise ValueError("Arduino CLI did not report its package directory")
    return Path(result)


def build(prepare=True):
    """Compile from pinned source and create a deterministic artifact manifest."""
    if not shutil.which("arduino-cli"):
        raise ValueError("arduino-cli is required on the release-building computer")
    command("python3", ROOT / "scripts/stamp-firmware-version.py", "--check")
    if prepare:
        command("arduino-cli", "core", "update-index")
        command("arduino-cli", "core", "install", CORE)
        for library in LIBRARIES:
            command("arduino-cli", "lib", "install", library)
    with tempfile.TemporaryDirectory(prefix="virtualglove-matrix-") as temporary:
        build_path = Path(temporary) / "build"
        command("arduino-cli", "compile", "--fqbn", COMPILE_FQBN,
                "--build-path", build_path, ROOT / "sketch")
        platform = package_directory() / "packages/arduino/hardware/zephyr/1.0.0"
        sources = {
            "virtualglove-matrix.elf-zsk.bin": build_path / "sketch.ino.elf-zsk.bin",
            "zephyr-arduino_uno_q_stm32u585xx.elf":
                platform / "firmwares/zephyr-arduino_uno_q_stm32u585xx.elf",
            "flash_sketch.cfg":
                platform / "variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg",
        }
        missing = [str(path) for path in sources.values() if not path.is_file()]
        if missing:
            raise ValueError("Arduino platform did not produce expected artifacts: " + ", ".join(missing))
        header = (ROOT / "sketch/firmware_version.h").read_text()
        match = re.search(r'VIRTUALGLOVE_FIRMWARE_ID "([0-9a-f]{64})"', header)
        if not match:
            raise ValueError("Generated firmware source identity is missing")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for name, source in sources.items():
            shutil.copy2(str(source), str(OUTPUT / name))
        artifacts = {
            name: {"sha256": digest(OUTPUT / name), "size": (OUTPUT / name).stat().st_size}
            for name in sorted(sources)
        }
        manifest = {
            "format": 1,
            "fqbn": FQBN,
            "platform": CORE,
            "boot_mode": "wait_for_app",
            "firmware_source_id": match.group(1),
            "artifacts": artifacts,
        }
        (OUTPUT / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("Built precompiled Matrix firmware in " + str(OUTPUT))


def main():
    """Parse the optional offline-ready build switch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-prepare", action="store_true",
                        help="use already installed exact platform and library versions")
    args = parser.parse_args()
    build(prepare=not args.skip_prepare)


if __name__ == "__main__":
    main()
