#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-batocera-nestopia-powerglove.sh
# Purpose: Cross-build the native Nestopia core with Batocera's exact target toolchain.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added exact-target Batocera cross-compilation.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

usage() {
  echo "Usage: $0 BATOCERA_SOURCE TARGET [DESTINATION]" >&2
  echo "Example: $0 /path/to/batocera.linux bcm2711" >&2
  exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
batocera=$(CDPATH= cd -- "$1" && pwd)
target=$2
destination=${3:-"$root/build/batocera-$target-nestopia-powerglove"}

[ -f "$batocera/Makefile" ] || { echo "Not a Batocera source tree: $batocera" >&2; exit 1; }
case "$target" in
  bcm2835) platform=rpi1 ;;
  bcm2836) platform=rpi2 ;;
  bcm2837) platform=rpi3_64 ;;
  bcm2711) platform=rpi4_64 ;;
  bcm2712) platform=rpi5_64 ;;
  x86_64|rk3326|rk3399|rk3568|rk3588|s905|s905gen2|s905gen3|s922x|sm8250) platform=unix ;;
  *) echo "Unsupported or unverified Batocera target: $target" >&2; exit 1 ;;
esac

# Building Batocera's stock Nestopia package first initializes the exact target
# sysroot and compiler without building a complete image.
make -C "$batocera" "$target-pkg" PKG=libretro-nestopia
host="$batocera/output/$target/host/bin"
cxx=$(find "$host" -maxdepth 1 \( -type f -o -type l \) -name '*-g++' | head -n 1)
[ -n "$cxx" ] || { echo "Batocera target compiler was not produced in $host" >&2; exit 1; }
prefix=${cxx%-g++}
cc="$prefix-gcc"
ar="$prefix-ar"
[ -x "$cc" ] && [ -x "$ar" ] || { echo "Incomplete Batocera target toolchain" >&2; exit 1; }

CC="$cc" CXX="$cxx" AR="$ar" VIRTUALGLOVE_LIBRETRO_PLATFORM="$platform" \
  "$root/scripts/build-nestopia-powerglove.sh" "$destination" >/dev/null
core="$destination/nestopia_powerglove_libretro.so"
[ -f "$core" ] || { echo "Batocera core build did not produce $core" >&2; exit 1; }

case "$(file -b "$core")" in
  *ELF*shared*object*) ;;
  *) echo "The result is not a Batocera ELF shared core" >&2; exit 1 ;;
esac
printf '%s\n' "$core"
