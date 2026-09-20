#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-batocera-native-matrix.sh
# Purpose: Build or resume every supported Batocera native-core target.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-18 - Added resumable verification for the complete Batocera matrix.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
  echo "Usage: $0 BATOCERA_SOURCE [DESTINATION]" >&2
  exit 2
}

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=$1
destination=${2:-"$root/native/batocera"}
version=$(sed -n 's/^BATOCERA_SYSTEM_VERSION = //p' \
  "$source_tree/package/batocera/core/batocera-system/batocera-system.mk" | head -n 1)
[ -n "$version" ] || { echo "Batocera version is unavailable." >&2; exit 1; }

for target in bcm2835 bcm2836 bcm2837 bcm2711 bcm2712 x86_64 \
  rk3326 rk3399 rk3568 rk3588 s905 s905gen2 s905gen3 s922x sm8250; do
  core="$destination/$target/$version/nestopia_powerglove_libretro.so"
  if [ -f "$destination/manifest.json" ] && [ -f "$core" ] && \
      python3 "$root/scripts/verify-batocera-native-core.py" \
        --manifest "$destination/manifest.json" --core "$core" \
        --arch "$target" --version "$version" >/dev/null 2>&1; then
    echo "SKIP  Verified Batocera $target $version"
    continue
  fi
  "$root/scripts/build-batocera-nestopia-powerglove.sh" \
    "$source_tree" "$target" "$destination"
done

echo "PASS  Built or verified the complete Batocera target matrix in $destination"
