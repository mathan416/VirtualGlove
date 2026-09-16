#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-recalbox-native-matrix.sh
# Purpose: Build every Recalbox native-core target from one exact release tree.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-15 - Added the complete Recalbox target build matrix.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
  echo "Usage: $0 RECALBOX_SOURCE [DESTINATION]" >&2
  exit 2
}

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=$1
destination=${2:-"$root/build/recalbox-native"}

for target in rpizero2 rpi3 rpi4_64 rpi5_64 rg353x odroidgo2 x86_64; do
  "$root/scripts/build-recalbox-nestopia-powerglove.sh" \
    "$source_tree" "$target" "$destination"
done

echo "PASS  Built the complete Recalbox target matrix in $destination"
