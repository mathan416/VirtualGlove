#!/usr/bin/env bash
# Export the VirtualGlove enclosure parts with OpenSCAD.
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

export_part uno_base virtualglove-uno-base
export_part uno_lid virtualglove-uno-lid
export_part dock_base virtualglove-dock-base
export_part dock_lid virtualglove-dock-lid
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
export_part usb_c_coupon virtualglove-usb-c-fit-coupon
export_part hub_coupon virtualglove-hub-fit-coupon

echo "STL files written to ${OUTPUT}"
