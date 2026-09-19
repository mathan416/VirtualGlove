#!/usr/bin/env bash
# Project: VirtualGlove
# File: hardware/enclosures/export-stl.sh
# Purpose: Export every maintained printable enclosure part with OpenSCAD.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added recessed logo inserts and multicolour 3MF exports.
#   2026-09-19 - Added the fully enclosed Controller Dock V2 parts.
# Full history: docs/CHANGELOG.md and Git history.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${SCRIPT_DIR}/virtualglove-controller.scad"
OUTPUT="${SCRIPT_DIR}/stl"
OPENSCAD="${OPENSCAD:-openscad}"

mkdir -p "${OUTPUT}"

export_part() {
  local part="$1"
  local name="$2"
  echo "Exporting ${name}..."
  "${OPENSCAD}" -D "part=\"${part}\"" --export-format binstl \
    -o "${OUTPUT}/${name}.stl" "${SOURCE}"
}

export_3mf() {
  local part="$1"
  local name="$2"
  echo "Exporting ${name}..."
  "${OPENSCAD}" -D "part=\"${part}\"" --export-format 3mf \
    -o "${OUTPUT}/${name}.3mf" "${SOURCE}"
}

export_part uno_base virtualglove-uno-base
export_part uno_lid virtualglove-uno-lid
export_part uno_lid_full_logo virtualglove-uno-lid-full-logo
export_part dock_base virtualglove-dock-base
export_part dock_lid virtualglove-dock-lid
export_part dock_lid_full_logo virtualglove-dock-lid-full-logo
export_part dock_v2_base virtualglove-dock-v2-base
export_part dock_v2_lid virtualglove-dock-v2-lid
export_part dock_v2_lid_full_logo virtualglove-dock-v2-lid-full-logo
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
export_3mf full_logo_multicolor virtualglove-full-logo-multicolor

echo "STL files written to ${OUTPUT}"
