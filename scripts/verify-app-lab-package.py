#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/verify-app-lab-package.py
# Purpose: Reject incomplete, unsafe, or private content in the generated App Lab installation ZIP.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Require verified precompiled Matrix firmware and exclude sketch sources.
#   2026-09-11 - Required the Engineering Toolkit PDF exposed by Controller Help.
#   2026-09-09 - Required validated MediaPipe 0.10.35 as the sole runtime wheel.
#   2026-09-07 - Aligned packaged PDFs with the consolidated documentation set.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Require the extracted Setup browser module.
#   2026-09-06 - Required the Rock Paper Scissors browser module.
#   2026-09-05 - Required the fixed, guided, and replay vision benchmark tools.
#   2026-09-05 - Required the guarded UNO Q USB camera recovery helper.
#   2026-09-05 - Required the corrected closed-hand Academy illustration.
#   2026-09-03 - Added repeatable installation-package content and path verification.
#   2026-09-03 - Required the offline Help renderer in every installation ZIP.
#   2026-09-03 - Required only the allowlisted public PDF editions.
#   2026-09-03 - Required the complete host shutdown-helper installation set.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.

"""Verify the generated UNO Q App Lab installation ZIP before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
import stat
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = ROOT / "output" / "app-lab" / "VirtualGlove-Uno-Q.zip"
PACKAGE_ROOT = PurePosixPath("VirtualGlove")
ENGINEERING_FILES = runpy.run_path(str(ROOT / "scripts/package-inventory.py"))["ENGINEERING_FILES"]
PUBLIC_PDF_NAMES = {
    "VirtualGlove-Third-Party-Notices.pdf",
    "VirtualGlove-Build-Your-Own.pdf",
    "VirtualGlove-Native-Emulation.pdf",
    "VirtualGlove-Troubleshooting.pdf",
    "VirtualGlove-Camera-Guide.pdf",
    "VirtualGlove-Enclosure-Quick-Reference.pdf",
    "VirtualGlove-Enclosure-Guide.pdf",
    "VirtualGlove-Engineering-Journey.pdf",
    "VirtualGlove-Engineering-Toolkit.pdf",

    "VirtualGlove-Matrix-Guide.pdf",
    "VirtualGlove-Architecture.pdf",
    "VirtualGlove-Changelog.pdf",
    "VirtualGlove-Configuration-Reference.pdf",
    "VirtualGlove-Contributing.pdf",
    "VirtualGlove-Gameplay-Guide.pdf",
    "VirtualGlove-Guide.pdf",
    "VirtualGlove-Overview.pdf",
    "VirtualGlove-Security.pdf",
    "VirtualGlove-Input-Audit.pdf",
    "VirtualGlove-Super-Glove-Ball-Native.pdf",
    "VirtualGlove-Direction-Response.pdf",
}
PUBLIC_PDF_PATHS = {f"output/pdf/{name}" for name in PUBLIC_PDF_NAMES}
REQUIRED_FILES = {
    "VirtualGlove/docs/BUILD_YOUR_OWN.md",
    "VirtualGlove/docs/NATIVE_EMULATION_EXPLAINED.md",
    "VirtualGlove/docs/TROUBLESHOOTING.md",
    "VirtualGlove/docs/CAMERA_GUIDE.md",
    "VirtualGlove/docs/ENCLOSURE_QUICK_REFERENCE.md",
    "VirtualGlove/docs/ENCLOSURE_GUIDE.md",
    "VirtualGlove/hardware/enclosures/virtualglove-controller.scad",
    "VirtualGlove/hardware/enclosures/export-stl.sh",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-uno-case-exterior.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-exterior.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-printable-branding.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-uno-case-back.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-uno-case-left.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-uno-case-right.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-uno-case-exploded.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-back.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-left.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-right.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-exploded.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-exterior.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-back.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-left.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-right.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-exploded.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-controller-dock-v2-port-access.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-parts.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-uno.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-dock-v1.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-dock-v1-finish.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-dock-v2.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-dock-v2-finish.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-enclosure-quick-reference-finish.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-lid-logo-options.png",
    "VirtualGlove/hardware/enclosures/previews/virtualglove-branding-insets.png",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-uno-base.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-uno-lid.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-uno-lid-full-logo.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-base.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-lid.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-lid-full-logo.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-v2-base.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-v2-lid.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-dock-v2-lid-full-logo.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-matrix-bezel.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-usb-c-fit-coupon.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-hub-fit-coupon.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-lid-logo-backing.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-lid-logo-cyan.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-lid-logo-red.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-lid-logo-multicolor.3mf",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-full-logo-backing.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-full-logo-cyan.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-full-logo-red.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-full-logo-multicolor.3mf",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-compact-full-logo-backing.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-compact-full-logo-cyan.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-compact-full-logo-red.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-compact-full-logo-multicolor.3mf",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-target-badge-backing.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-target-badge-cyan.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-target-badge-red.stl",
    "VirtualGlove/hardware/enclosures/stl/virtualglove-target-badge-multicolor.3mf",

    "VirtualGlove/src/virtualglove/diagnostic_trace.py",
    "VirtualGlove/scripts/measure-dot-input.py",
    "VirtualGlove/scripts/install-powerglove-dot.sh",
    "VirtualGlove/native/powerglove-dot/powerglove_dot.cpp",
    "VirtualGlove/src/virtualglove/dot_launcher.py",
    "VirtualGlove/retropie/bin/virtualglove-dot",
    "VirtualGlove/src/virtualglove/controller_protocol.py",
    "VirtualGlove/src/virtualglove/web_common.py",
    "VirtualGlove/src/virtualglove/dashboard_web.py",
    "VirtualGlove/src/virtualglove/academy_web.py",
    "VirtualGlove/src/virtualglove/games_web.py",
    "VirtualGlove/src/virtualglove/tuning_web.py",

    "VirtualGlove/scripts/install-uno-q.sh",
    "VirtualGlove/scripts/install-retropie.sh",
    "VirtualGlove/scripts/install-recalbox.sh",
    "VirtualGlove/scripts/install-batocera.sh",
    "VirtualGlove/scripts/install-package.py",
    "VirtualGlove/scripts/setup-machine.py",
    "VirtualGlove/scripts/installation-manifest.py",
    "VirtualGlove/docs/images/web/gestures/v2/v-sign.png",
    "VirtualGlove/docs/images/gestures/v2/pixel-pal-coach.png",
    "VirtualGlove/docs/images/gestures/v2/pixel-pal-ready.png",
    "VirtualGlove/docs/images/gestures/v2/pixel-pal-thinking.png",
    "VirtualGlove/docs/images/gestures/v2/pixel-pal-safety.png",
    "VirtualGlove/docs/images/gestures/v2/pixel-pal-success.png",
    "VirtualGlove/docs/images/web/gestures/v2/pixel-pal-coach.png",
    "VirtualGlove/docs/images/web/gestures/v2/pixel-pal-ready.png",
    "VirtualGlove/docs/images/web/gestures/v2/pixel-pal-thinking.png",
    "VirtualGlove/docs/images/web/gestures/v2/pixel-pal-safety.png",
    "VirtualGlove/docs/images/web/gestures/v2/pixel-pal-success.png",
    "VirtualGlove/docs/images/web/gestures/actions/v-sign.png",
    "VirtualGlove/scripts/uno-q-early-start.py",
    "VirtualGlove/uno-q/virtualglove-early-start.service",
    "VirtualGlove/scripts/flash-matrix-firmware.py",
    "VirtualGlove/firmware/matrix/manifest.json",
    "VirtualGlove/firmware/matrix/virtualglove-matrix.elf-zsk.bin",
    "VirtualGlove/firmware/matrix/zephyr-arduino_uno_q_stm32u585xx.elf",
    "VirtualGlove/firmware/matrix/flash_sketch.cfg",
    "VirtualGlove/docs/MATRIX_GUIDE.md",
    "VirtualGlove/src/virtualglove/_build_info.json",
    "VirtualGlove/src/virtualglove/versioning.py",
    "VirtualGlove/models/hand_landmarker.task",
    "VirtualGlove/models/SHA256SUMS",
    "VirtualGlove/licenses/Apache-2.0.txt",
    "VirtualGlove/licenses/GPL-2.0.txt",
    "VirtualGlove/THIRD_PARTY_NOTICES.md",
    "VirtualGlove/src/virtualglove/game_registry.py",
    "VirtualGlove/src/virtualglove/tuning.py",
    "VirtualGlove/src/virtualglove/realtime.py",
    "VirtualGlove/src/virtualglove/native_state.py",
    "VirtualGlove/scripts/build-nestopia-powerglove.sh",
    "VirtualGlove/scripts/install-nestopia-powerglove.sh",
    "VirtualGlove/scripts/configure-super-glove-ball-core.py",
    "VirtualGlove/native/nestopia-powerglove/nestopia-powerglove.patch",
    "VirtualGlove/docs/super-glove-ball-native.md",
    "VirtualGlove/docs/direction-response-benchmark.md",
    "VirtualGlove/docs/ENGINEERING_JOURNEY.md",
    "VirtualGlove/docs/power-glove-rom-input-audit.md",
    "VirtualGlove/docs/images/gestures/actions/menu-guard.png",
    "VirtualGlove/docs/images/web/gestures/actions/menu-guard.png",
    "VirtualGlove/docs/images/gestures/actions/close-all-fingers.png",
    "VirtualGlove/docs/images/web/gestures/actions/close-all-fingers.png",
    "VirtualGlove/src/virtualglove/setup_web.py",
    "VirtualGlove/src/virtualglove/wifi_status.py",
    "VirtualGlove/uno-q/virtualglove-wifi-status.py",
    "VirtualGlove/uno-q/virtualglove-wifi-status.service",
    "VirtualGlove/uno-q/virtualglove-wifi-status.timer",
    "VirtualGlove/src/virtualglove/play_game.py",
    "VirtualGlove/retropie/virtualglove-receiver.service",
    "VirtualGlove/retropie/virtualglove-receiver.timer",
    "VirtualGlove/retropie/virtualglove-games.service",
    "VirtualGlove/retropie/runcommand-onstart-virtualglove.sh",
    "VirtualGlove/retropie/runcommand-onend-virtualglove.sh",
    "VirtualGlove/retropie/bin/virtualglove-receiver",
    "VirtualGlove/retropie/bin/virtualglove-games",
    "VirtualGlove/retropie/bin/virtualglove-pair",
    "VirtualGlove/retropie/bin/virtualglove-profile",
    "VirtualGlove/retropie/bin/virtualglove-retropie-hook",
    "VirtualGlove/retropie/bin/virtualglove-bsb-zap",
    "VirtualGlove/src/virtualglove/console_monitor.py",
    "VirtualGlove/src/virtualglove/merged_gamepad.py",
    "VirtualGlove/recalbox/virtualglove-service",
    "VirtualGlove/recalbox/virtualglove-core-mount",
    "VirtualGlove/recalbox/retroarch-nes.cfg",
    "VirtualGlove/scripts/build-recalbox-nestopia-powerglove.sh",
    "VirtualGlove/scripts/install-recalbox-nestopia-powerglove.sh",
    "VirtualGlove/scripts/configure-recalbox-super-glove-ball-core.py",
    "VirtualGlove/batocera/VirtualGlove",
    "VirtualGlove/batocera/virtualglove-game",
    "VirtualGlove/batocera/virtualglove-core-mount",
    "VirtualGlove/batocera/retroarch-nes.cfg",
    "VirtualGlove/scripts/build-batocera-nestopia-powerglove.sh",
    "VirtualGlove/scripts/install-batocera-nestopia-powerglove.sh",
    "VirtualGlove/scripts/configure-batocera-super-glove-ball-core.py",
    "VirtualGlove/src/virtualglove/retroarch_remote.py",
    "VirtualGlove/src/virtualglove/launchbox_hook.py",
    "VirtualGlove/src/virtualglove/retroarch_hotkeys.py",
    "VirtualGlove/src/virtualglove/launchbox_runtime.py",
    "VirtualGlove/launchbox/install-launchbox.ps1",
    "VirtualGlove/launchbox/virtualglove-launchbox.cmd",
    "VirtualGlove/launchbox/virtualglove-pair.ps1",
    "VirtualGlove/launchbox/virtualglove-restart-runtime.cmd",
    "VirtualGlove/launchbox/configure-launchbox-emulator.ps1",
    "VirtualGlove/launchbox/retroarch-nes.cfg",
    "VirtualGlove/launchbox/retroarch-native.cfg",
    "VirtualGlove/scripts/build-launchbox-nestopia-powerglove.sh",
    "VirtualGlove/scripts/verify-launchbox-native-core.py",
    "VirtualGlove/native/launchbox/nestopia-windows.patch",
    "VirtualGlove/native/launchbox/manifest.json",
    "VirtualGlove/native/launchbox/x86_64/nestopia_powerglove_libretro.dll",
    "VirtualGlove/native/launchbox/x86_64/nestopia-powerglove-source.tar.gz",
    "VirtualGlove/bricks/local/profile_control/brick_config.yaml",
    "VirtualGlove/bricks/local/profile_control/brick_compose.yaml",
    "VirtualGlove/scripts/profile-relay.py",
    "VirtualGlove/LICENSE",
    "VirtualGlove/README.md",
    "VirtualGlove/app.yaml",
    "VirtualGlove/bricks/local/avahi_resolver/brick_config.yaml",
    "VirtualGlove/bricks/local/avahi_resolver/brick_compose.yaml",
    "VirtualGlove/scripts/avahi-resolver-service.py",
    "VirtualGlove/docs/CONFIGURATION_REFERENCE.md",
    "VirtualGlove/docs/CONTRIBUTING.md",
    "VirtualGlove/docs/SECURITY.md",
    "VirtualGlove/python/main.py",
    "VirtualGlove/scripts/install-uno-q-shutdown-helper.sh",
    "VirtualGlove/scripts/install-uno-q-camera-recovery-helper.sh",
    "VirtualGlove/src/virtualglove/runtime_assets.py",
    "VirtualGlove/src/virtualglove/help_content.py",
    "VirtualGlove/uno-q/virtualglove-system-shutdown.conf",
    "VirtualGlove/uno-q/virtualglove-system-shutdown.path",
    "VirtualGlove/uno-q/virtualglove-system-shutdown.service",
    "VirtualGlove/uno-q/virtualglove-camera-recovery.py",
    "VirtualGlove/uno-q/virtualglove-camera-recovery.conf",
    "VirtualGlove/uno-q/virtualglove-camera-recovery.path",
    "VirtualGlove/uno-q/virtualglove-camera-recovery.service",
} | {f"VirtualGlove/{path}" for path in PUBLIC_PDF_PATHS}
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", "data", "tests", "tmp"}
FORBIDDEN_NAMES = {"CODE_REVIEW_MAP.txt", ".DS_Store", "cheatsheet.md"}
FORBIDDEN_SUFFIXES = {".pyc"}
LEGACY_RUNTIME_FILES = {
    "VirtualGlove/retropie/powerglove-receiver.service",
    "VirtualGlove/retropie/powerglove-receiver.timer",
    "VirtualGlove/retropie/powerglove-games.service",
    "VirtualGlove/retropie/runcommand-onstart-powerglove.sh",
    "VirtualGlove/retropie/runcommand-onend-powerglove.sh",
    *{"VirtualGlove/retropie/bin/powerglove-" + name for name in (
        "bsb-zap", "dot", "games", "pair", "profile", "receiver", "retropie-hook"
    )},
    *{"VirtualGlove/uno-q/powerglove-" + name for name in (
        "early-start.service", "wifi-status.py", "wifi-status.service", "wifi-status.timer",
        "system-shutdown.conf", "system-shutdown.path", "system-shutdown.service",
        "camera-recovery.py", "camera-recovery.conf", "camera-recovery.path",
        "camera-recovery.service",
    )},
}
EXECUTABLE_RUNTIME_FILES = {
    "VirtualGlove/batocera/VirtualGlove",
    "VirtualGlove/batocera/virtualglove-game",
    "VirtualGlove/batocera/virtualglove-core-mount",
}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of an archive read in bounded blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_errors(path: Path) -> list[str]:
    """Return content, traversal, and accidental-disclosure errors for one ZIP."""
    errors = []
    try:
        with ZipFile(path) as archive:
            build_identity = {}
            bad_member = archive.testzip()
            if bad_member:
                errors.append(f"corrupt member: {bad_member}")
            names = {info.filename for info in archive.infolist() if not info.is_dir()}
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    errors.append(f"unsafe archive path: {info.filename}")
                if not member.parts or member.parts[0] != PACKAGE_ROOT.name:
                    errors.append(f"member outside {PACKAGE_ROOT}/: {info.filename}")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    errors.append(f"symbolic link is not allowed in the App Lab installation ZIP: {info.filename}")
                relative_parts = set(member.parts[1:])
                relative = PurePosixPath(*member.parts[1:])
                if relative.parts[:2] == ("assets", "matrix"):
                    errors.append(f"local duplicate matrix export included: {info.filename}")
                if relative_parts & FORBIDDEN_PARTS:
                    errors.append(f"private or generated path included: {info.filename}")
                if member.name in FORBIDDEN_NAMES or member.suffix in FORBIDDEN_SUFFIXES:
                    errors.append(f"forbidden file included: {info.filename}")
                if not info.is_dir() and "output" in relative_parts and str(relative) not in PUBLIC_PDF_PATHS:
                    errors.append(f"unapproved output file included: {info.filename}")
                if member.suffix == ".pdf" and str(relative) not in PUBLIC_PDF_PATHS:
                    errors.append(f"unapproved PDF included: {info.filename}")
            for name in names:
                if name.startswith("VirtualGlove/docs/images/gestures/") and name.endswith(".png") and not name.endswith("-web.png"):
                    compact = name.replace("/docs/images/gestures/", "/docs/images/web/gestures/", 1)
                    if compact not in names:
                        errors.append("missing compact gesture image: " + compact)
            for name in sorted(REQUIRED_FILES - names):
                errors.append(f"required package file is missing: {name}")
            for name in sorted(LEGACY_RUNTIME_FILES & names):
                errors.append(f"legacy PowerGlove runtime file included: {name}")
            info_by_name = {info.filename: info for info in archive.infolist()}
            for name in sorted(EXECUTABLE_RUNTIME_FILES & names):
                if not (info_by_name[name].external_attr >> 16) & 0o111:
                    errors.append(f"runtime entry point is not executable: {name}")
            for relative in sorted(ENGINEERING_FILES):
                name = "VirtualGlove/" + relative
                if name in names:
                    errors.append(f"engineering-only file included in ordinary package: {name}")
            stamp = "VirtualGlove/src/virtualglove/_build_info.json"
            if stamp in names:
                try:
                    build_identity = json.loads(archive.read(stamp))
                    if (not build_identity.get("version") or not build_identity.get("branch")
                            or build_identity["branch"] == "unknown"):
                        errors.append("build version or branch is missing")
                except (ValueError, AttributeError):
                    errors.append("invalid build identity")
            model = "VirtualGlove/models/hand_landmarker.task"
            if model in names and hashlib.sha256(archive.read(model)).hexdigest() != "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1":
                errors.append("bundled Hand Landmarker checksum mismatch")
            firmware_root = "VirtualGlove/firmware/matrix/"
            firmware_manifest = firmware_root + "manifest.json"
            if firmware_manifest in names:
                try:
                    firmware = json.loads(archive.read(firmware_manifest))
                    expected = {"format": 1, "fqbn": "arduino:zephyr:unoq",
                                "platform": "arduino:zephyr@1.0.0",
                                "boot_mode": "wait_for_app"}
                    if any(firmware.get(key) != value for key, value in expected.items()):
                        errors.append("precompiled Matrix firmware identity is unsupported")
                    if not re.fullmatch(r"[0-9a-f]{64}", firmware.get("firmware_source_id", "")):
                        errors.append("precompiled Matrix source identity is invalid")
                    if firmware.get("firmware_source_id") != build_identity.get("firmware_expected"):
                        errors.append("precompiled Matrix firmware does not match the packaged application")
                    expected_artifacts = {"virtualglove-matrix.elf-zsk.bin",
                                          "zephyr-arduino_uno_q_stm32u585xx.elf",
                                          "flash_sketch.cfg"}
                    if set(firmware.get("artifacts", {})) != expected_artifacts:
                        errors.append("precompiled Matrix manifest is incomplete")
                    for artifact in expected_artifacts:
                        member = firmware_root + artifact
                        record = firmware.get("artifacts", {}).get(artifact, {})
                        data = archive.read(member)
                        if (record.get("size") != len(data) or
                                record.get("sha256") != hashlib.sha256(data).hexdigest()):
                            errors.append("precompiled Matrix artifact mismatch: " + artifact)
                    official = {
                        "zephyr-arduino_uno_q_stm32u585xx.elf":
                            "39d4a4fd47241663323f6e04f94dd8f5a9f9ad6582cf1df37f9709b74026adcd",
                        "flash_sketch.cfg":
                            "38706cee1f9ff2e53364a47129d1c1aea9bb9687ed26d7d70b4a9f9bc5bca60c",
                    }
                    for artifact, checksum in official.items():
                        if firmware.get("artifacts", {}).get(artifact, {}).get("sha256") != checksum:
                            errors.append("unpinned Arduino firmware artifact: " + artifact)
                except (ValueError, KeyError, AttributeError):
                    errors.append("invalid precompiled Matrix firmware manifest")
            for sketch_source in ("VirtualGlove/sketch/sketch.yaml",
                                  "VirtualGlove/sketch/sketch.ino"):
                if sketch_source in names:
                    errors.append("source-build Matrix file included in ordinary package: " + sketch_source)
            license_path = "VirtualGlove/licenses/Apache-2.0.txt"
            if license_path in names and hashlib.sha256(archive.read(license_path)).hexdigest() != "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30":
                errors.append("Apache 2.0 license text is missing or altered")
            wheels = {
                PurePosixPath(name).name for name in names
                if "/python/worker-wheels/mediapipe-" in name and name.endswith(".whl")
            }
            required_wheels = {
                "mediapipe-0.10.35+powerglove.cpu1-cp312-cp312-linux_aarch64.whl"
            }
            if wheels != required_wheels:
                errors.append(
                    "expected validated UNO Q MediaPipe 0.10.35 wheel only"
                )
    except (BadZipFile, FileNotFoundError) as exc:
        errors.append(str(exc))
    return errors


def build_parser() -> argparse.ArgumentParser:
    """Create the installation-package verification command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=DEFAULT_ARCHIVE)
    return parser


def main() -> int:
    """Verify an archive, print its digest, and return a CI-friendly status."""
    path = build_parser().parse_args().archive
    errors = archive_errors(path)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"App Lab installation ZIP verified: {path}")
    print(f"SHA-256: {sha256_file(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
