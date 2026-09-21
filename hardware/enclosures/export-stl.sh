#!/usr/bin/env bash
# Project: VirtualGlove
# File: hardware/enclosures/export-stl.sh
# Purpose: Export every maintained printable enclosure part with OpenSCAD.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Preserved the Anycubic-assigned full-logo project during exports.
#   2026-09-19 - Added recessed logo inserts and multicolour 3MF exports.
#   2026-09-20 - Added photo-validated Controller Dock V2.1 parts and coupons;
#                V2.1 supersedes the withdrawn V2 print.
# Full history: docs/CHANGELOG.md and Git history.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${SCRIPT_DIR}/virtualglove-controller.scad"
OUTPUT="${SCRIPT_DIR}/stl"
OPENSCAD="${OPENSCAD:-openscad}"

# OpenSCAD's current universal macOS build can select an arm64 Qt path that
# incorrectly reports missing NEON support until the GUI has been opened.
# Rosetta's x86_64 slice works headlessly, so use it when the requested command
# cannot start rather than leaving the enclosure export half-finished.
OPENSCAD_COMMAND=("${OPENSCAD}")
MAC_OPENSCAD="/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
if [[ "${OPENSCAD}" == "openscad" && "$(uname -s)" == "Darwin" &&
      "$(uname -m)" == "arm64" && -x "${MAC_OPENSCAD}" ]] && \
   /usr/bin/arch -x86_64 "${MAC_OPENSCAD}" --version >/dev/null 2>&1; then
  echo "Using OpenSCAD's headless-safe x86_64 app slice on Apple Silicon."
  OPENSCAD_COMMAND=(/usr/bin/arch -x86_64 "${MAC_OPENSCAD}")
elif ! "${OPENSCAD_COMMAND[@]}" --version >/dev/null 2>&1; then
  echo "OpenSCAD could not start. Open the app once, then rerun this exporter." >&2
  exit 1
fi

mkdir -p "${OUTPUT}"

export_part() {
  local part="$1"
  local name="$2"
  local target="${OUTPUT}/${name}.stl"
  local temporary="${target}.new"
  echo "Exporting ${name}..."
  rm -f "${temporary}"
  "${OPENSCAD_COMMAND[@]}" -D "part=\"${part}\"" --export-format binstl \
    -o "${temporary}" "${SOURCE}"
  [[ -s "${temporary}" ]] || {
    echo "OpenSCAD did not create ${target}" >&2
    exit 1
  }
  mv "${temporary}" "${target}"
}

export_3mf() {
  local part="$1"
  local name="$2"
  local target="${OUTPUT}/${name}.3mf"
  local temporary="${target}.new"
  echo "Exporting ${name}..."
  rm -f "${temporary}"
  "${OPENSCAD_COMMAND[@]}" -D "part=\"${part}\"" --export-format 3mf \
    -o "${temporary}" "${SOURCE}"
  [[ -s "${temporary}" ]] || {
    echo "OpenSCAD did not create ${target}" >&2
    exit 1
  }
  mv "${temporary}" "${target}"
}

export_part uno_base virtualglove-uno-base
export_part uno_lid virtualglove-uno-lid
export_part uno_lid_full_logo virtualglove-uno-lid-full-logo
export_part dock_base virtualglove-dock-base
export_part dock_lid virtualglove-dock-lid
export_part dock_lid_full_logo virtualglove-dock-lid-full-logo
export_part dock_v21_base virtualglove-dock-v2-1-base
export_part dock_v21_lid virtualglove-dock-v2-1-lid
export_part dock_v21_lid_full_logo virtualglove-dock-v2-1-lid-full-logo
export_part dock_v21_mount_coupon virtualglove-dock-v2-1-mount-fit-coupon
export_part dock_v21_wordmark_coupon virtualglove-dock-v2-1-wordmark-fit-coupon
export_part matrix_bezel virtualglove-matrix-bezel
export_part lid_logo_backing virtualglove-lid-logo-backing
export_part lid_logo_cyan virtualglove-lid-logo-cyan
export_part lid_logo_red virtualglove-lid-logo-red
export_part target_badge_backing virtualglove-target-badge-backing
export_part target_badge_cyan virtualglove-target-badge-cyan
export_part target_badge_red virtualglove-target-badge-red
export_part full_logo_backing virtualglove-full-logo-backing
export_part full_logo_cyan virtualglove-full-logo-cyan
export_part full_logo_red virtualglove-full-logo-red
export_part compact_full_logo_backing virtualglove-compact-full-logo-backing
export_part compact_full_logo_cyan virtualglove-compact-full-logo-cyan
export_part compact_full_logo_red virtualglove-compact-full-logo-red
export_part usb_c_coupon virtualglove-usb-c-fit-coupon
export_part hub_coupon virtualglove-hub-fit-coupon

export_3mf lid_logo_multicolor virtualglove-lid-logo-multicolor
export_3mf compact_full_logo_multicolor virtualglove-compact-full-logo-multicolor
export_3mf target_badge_multicolor virtualglove-target-badge-multicolor

# This file is a complete Anycubic Slicer Next project with ACE assignments,
# not only an OpenSCAD mesh. Re-exporting it directly would flatten every
# region back to the first filament. Its geometry can still be regenerated
# from the three full_logo_* STL parts when the design changes.
if [[ ! -f "${OUTPUT}/virtualglove-full-logo-multicolor.3mf" ]]; then
  echo "Missing maintained Anycubic project: virtualglove-full-logo-multicolor.3mf" >&2
  exit 1
fi
echo "Preserving virtualglove-full-logo-multicolor.3mf with its ACE assignments."

echo "STL files written to ${OUTPUT}"
