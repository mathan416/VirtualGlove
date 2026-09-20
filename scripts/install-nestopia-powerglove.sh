#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/install-nestopia-powerglove.sh
# Purpose: Build and install the separately named evidence-gated Nestopia core on RetroPie.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Installed the consolidated third-party notice and modification ledger.
#   2026-09-04 - Added isolated RetroPie installation with GPLv2 notices.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/build/nestopia-powerglove-retropie"}
target=/opt/retropie/libretrocores/lr-nestopia-powerglove
manifest="$root/native/retropie/manifest.json"
verifier="$root/scripts/verify-retropie-native-core.py"
retroarch=/opt/retropie/emulators/retroarch/bin/retroarch

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' "Run this installer with sudo on the RetroPie cabinet." >&2
  exit 1
fi

source_license="$destination/source/COPYING"
if [ -f "$manifest" ] && [ -f "$verifier" ]; then
  machine=$(uname -m)
  core=$(python3 "$verifier" --manifest "$manifest" --machine "$machine" \
    --runtime "$retroarch" --resolve-core)
  python3 "$verifier" --manifest "$manifest" --machine "$machine" \
    --runtime "$retroarch" --core "$core" --load
  source_archive=$(dirname "$core")/nestopia-powerglove-source.tar.gz
  license_work=$(mktemp -d)
  trap 'rm -rf "$license_work"' EXIT HUP INT TERM
  tar -xzf "$source_archive" -C "$license_work" ./COPYING
  source_license="$license_work/COPYING"
else
  core=$("$root/scripts/build-nestopia-powerglove.sh" "$destination")
  case "$core" in
    *.so) ;;
    *) printf '%s\n' "The native core must be built on the Linux RetroPie host." >&2; exit 1 ;;
  esac
fi
install -d -m 0755 "$target"
install -m 0644 "$core" "$target/nestopia_powerglove_libretro.so"
install -m 0644 "$source_license" "$target/COPYING"
install -m 0644 "$root/THIRD_PARTY_NOTICES.md" "$target/VIRTUALGLOVE-NOTICES.md"
printf '%s\n' "Installed $target/nestopia_powerglove_libretro.so"
printf '%s\n' "Use configure-super-glove-ball-core.py to opt one ROM into native mode or restore FCEUmm."
