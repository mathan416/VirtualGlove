#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/package-inventory.py
# Purpose: Separate ordinary installation content from developer and research tools.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Split the supported Engineering Toolkit from repository-only maintainer tools.
#   2026-09-09 - Added the end-user and Engineering Tools package boundary.
# Full history: docs/CHANGELOG.md and Git history.

"""Declare public toolkit and repository-only files omitted from ordinary installs."""

TOOLKIT_CATEGORIES = {
    "offline-analysis": (
        "scripts/analyze-latency-trace.py",
        "scripts/analyze-latency-video.py",
        "scripts/analyze-motion-trace.py",
        "scripts/benchmark-diagnostic-overhead.py",
        "scripts/benchmark-direction-response.py",
        "scripts/benchmark-frame-preprocessing.py",
        "scripts/benchmark-native-motion-curve.py",
        "scripts/benchmark-palm-anchors.py",
        "scripts/benchmark-post-inference.py",
    ),
    "camera-and-recognition": (
        "scripts/benchmark-camera-pipeline.py",
        "scripts/benchmark-staggered-trackers.py",
        "scripts/benchmark-tasks-live-stream.py",
        "scripts/benchmark-vision-replay.py",
        "scripts/guided-vision-benchmark.py",
        "scripts/soak-camera-exposure.py",
        "scripts/soak-full-vision-exposure.py",
    ),
    "live-system-tracing": (
        "scripts/manage-latency-traces.py",
        "scripts/measure-vision-status.py",
        "scripts/prepare-end-to-end-session.py",
        "scripts/run-native-latency-session.py",
    ),
    "native-and-accelerator-research": (
        "native/nestopia-powerglove/diagnostic_trace.h",
        "scripts/benchmark-ncnn-sidecar.py",
        "scripts/build-fceumm-benchmark.sh",
        "scripts/build-nestopia-powerglove.sh",
        "scripts/fetch-runtime-assets.sh",
        "scripts/instrument-native-core.py",
        "scripts/run-nestopia-powerglove-trace.py",
    ),
    "toolkit-support": (
        "scripts/check-engineering-toolkit.py",
        "scripts/setup-engineering-tools.py",
    ),
}

ENGINEERING_TOOLKIT_FILES = frozenset(
    name for files in TOOLKIT_CATEGORIES.values() for name in files
)

# The read-only status sampler remains useful in an ordinary installed payload
# as well as in the optional toolkit.
SHARED_DIAGNOSTIC_FILES = frozenset({
    "scripts/build-nestopia-powerglove.sh",
    "scripts/measure-vision-status.py",
})

MAINTAINER_FILES = frozenset({
    "scripts/application-payload.py",
    "scripts/build-app-lab-package.sh",
    "scripts/build-architecture-diagrams.py",
    "scripts/build-batocera-native-matrix.sh",
    "scripts/build-batocera-nestopia-powerglove.sh",
    "scripts/build-code-review-map.py",
    "scripts/build-docs-pdf.py",
    "scripts/build-engineering-tools-package.py",
    "scripts/build-gesture-crops.py",
    "scripts/build-help-images.py",
    "scripts/build-install-packages.py",
    "scripts/build-installer-scripts.py",
    "scripts/build-launchbox-nestopia-powerglove.sh",
    "scripts/build-matrix-animation-preview.py",
    "scripts/build-matrix-firmware.py",
    "scripts/build-matrix-letter-images.py",
    "scripts/build-recalbox-native-matrix.sh",
    "scripts/build-recalbox-nestopia-powerglove.sh",
    "scripts/capture-guide-screenshots.py",
    "scripts/check-documentation.py",
    "scripts/check-source-docs.py",
    "scripts/deploy-uno-q-wifi.sh",
    "scripts/make-enclosure-previews-transparent.py",
    "scripts/package-inventory.py",
    "scripts/run-tests.py",
    "scripts/stamp-build-version.py",
    "scripts/stamp-firmware-version.py",
    "scripts/templates/install.sh.in",
    "scripts/verify-app-lab-package.py",
})

ENGINEERING_FILES = (
    ENGINEERING_TOOLKIT_FILES - SHARED_DIAGNOSTIC_FILES
) | MAINTAINER_FILES


def is_engineering_file(name: str) -> bool:
    """Return whether a repository-relative path belongs only to engineering work."""
    return name in ENGINEERING_FILES
