#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-app-lab-package.sh
# Purpose: Build a clean, offline-model UNO Q App Lab distribution archive from tracked project sources.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Build and package pinned precompiled Matrix firmware.
#   2026-09-05 - Refreshed the tracked SHA-256 companion after every successful build.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Included allowlisted public PDF guides in installation packages.
# Full history: docs/CHANGELOG.md and Git history.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly OUTPUT_DIR="${PROJECT_DIR}/output/app-lab"
readonly OUTPUT_ZIP="${OUTPUT_DIR}/VirtualGlove-Uno-Q.zip"
readonly OUTPUT_SHA="${OUTPUT_ZIP}.sha256"
readonly OUTPUT_SHA_TMP="${OUTPUT_SHA}.tmp"
readonly PACKAGE_TMP="$(mktemp -d)"
# Remove the private staging directory regardless of build success or failure.
cleanup() {
  rm -rf "${PACKAGE_TMP}"
  rm -f "${OUTPUT_SHA_TMP}"
}
trap cleanup EXIT

mkdir -p "${OUTPUT_DIR}" "${PACKAGE_TMP}/VirtualGlove"
python3 "${SCRIPT_DIR}/build-enclosure-packages.py"
python3 "${SCRIPT_DIR}/build-matrix-firmware.py"
python3 "${SCRIPT_DIR}/application-payload.py" "${PACKAGE_TMP}/VirtualGlove" --precompiled-matrix

cd "${PACKAGE_TMP}"
zip -qr "${PACKAGE_TMP}/verified-package.zip" VirtualGlove
python3 "${SCRIPT_DIR}/verify-app-lab-package.py" "${PACKAGE_TMP}/verified-package.zip"
mv "${PACKAGE_TMP}/verified-package.zip" "${OUTPUT_ZIP}"
python3 - "${OUTPUT_ZIP}" "${OUTPUT_SHA_TMP}" <<'PY'
import hashlib
from pathlib import Path
import sys

archive = Path(sys.argv[1])
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
Path(sys.argv[2]).write_text(f"{digest}  {archive.name}\n")
PY
mv "${OUTPUT_SHA_TMP}" "${OUTPUT_SHA}"
echo "Built ${OUTPUT_ZIP} and ${OUTPUT_SHA}"
