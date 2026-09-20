#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/install-nestopia-powerglove.sh
# Purpose: Install the ABI-matched packaged Nestopia VirtualGlove core on RetroPie.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Installed the consolidated third-party notice and modification ledger.
#   2026-09-04 - Added isolated RetroPie installation with GPLv2 notices.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=/opt/retropie/libretrocores/lr-nestopia-powerglove
manifest="$root/native/retropie/manifest.json"
verifier="$root/scripts/verify-retropie-native-core.py"
retroarch=/opt/retropie/emulators/retroarch/bin/retroarch

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' "Run this installer with sudo on the RetroPie cabinet." >&2
  exit 1
fi

license_work=
temporary=
cleanup() {
  [ -z "$temporary" ] || rm -f "$temporary"
  [ -z "$license_work" ] || rm -rf "$license_work"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$manifest" ] || [ ! -f "$verifier" ]; then
  printf '%s\n' "ACTION  This package does not contain the verified RetroPie native-core matrix; the existing core was left unchanged and FCEUmm remains available." >&2
  exit 3
fi
machine=$(uname -m)
if ! core=$(python3 "$verifier" --manifest "$manifest" --machine "$machine" \
    --runtime "$retroarch" --resolve-core); then
  printf '%s\n' "ACTION  No compatible packaged RetroPie core was selected; the existing core was left unchanged and FCEUmm remains available." >&2
  exit 3
fi
if ! python3 "$verifier" --manifest "$manifest" --machine "$machine" \
    --runtime "$retroarch" --core "$core" --load; then
  printf '%s\n' "ACTION  The packaged RetroPie core did not load safely; the existing core was left unchanged and FCEUmm remains available." >&2
  exit 4
fi
source_archive=$(dirname "$core")/nestopia-powerglove-source.tar.gz
license_work=$(mktemp -d)
tar -xzf "$source_archive" -C "$license_work" ./COPYING
source_license="$license_work/COPYING"
install -d -m 0755 "$target"
installed="$target/nestopia_powerglove_libretro.so"
if [ ! -f "$installed" ] || ! cmp -s "$core" "$installed"; then
  if [ -f "$installed" ]; then
    backup=/var/backups/virtualglove/nestopia-powerglove/$(date -u +%Y%m%d-%H%M%S)
    install -d -m 0700 "$backup"
    cp -p "$installed" "$backup/"
    [ ! -f "$target/COPYING" ] || cp -p "$target/COPYING" "$backup/"
    [ ! -f "$target/VIRTUALGLOVE-NOTICES.md" ] || \
      cp -p "$target/VIRTUALGLOVE-NOTICES.md" "$backup/"
    printf '%s\n' "Backed up the previous native core to $backup"
  fi
  temporary="$target/.nestopia_powerglove_libretro.so.new.$$"
  install -m 0644 "$core" "$temporary"
  cmp -s "$core" "$temporary" || {
    printf '%s\n' "The staged native core did not verify after copying." >&2
    exit 1
  }
  mv -f "$temporary" "$installed"
  temporary=
fi
install -m 0644 "$source_license" "$target/COPYING"
install -m 0644 "$root/THIRD_PARTY_NOTICES.md" "$target/VIRTUALGLOVE-NOTICES.md"
printf '%s\n' "Installed and verified $installed"
printf '%s\n' "Use configure-super-glove-ball-core.py to opt one ROM into native mode or restore FCEUmm."
