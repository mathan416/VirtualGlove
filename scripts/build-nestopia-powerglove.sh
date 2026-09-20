#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-nestopia-powerglove.sh
# Purpose: Build the isolated evidence-gated Nestopia PowerGlove native core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added the pinned custom Nestopia core build.
#   2026-09-04 - Guarded the original Nestopia Power Glove source header.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

usage() {
  cat <<'EOF'
Usage: scripts/build-nestopia-powerglove.sh [DESTINATION]

Clone the pinned Nestopia source, apply the isolated VirtualGlove native-input
patch, and build a local libretro core. The command never installs the result.
DESTINATION defaults to build/nestopia-powerglove.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  -*)
    echo "error: unsupported option: $1" >&2
    usage >&2
    exit 2
    ;;
esac
[ "$#" -le 1 ] || { usage >&2; exit 2; }

revision=5a1cd378cb46ca9ccc2dd6f8b2b6a79ab986052e
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/build/nestopia-powerglove"}
source_dir="$destination/source"

mkdir -p "$destination"
if [ ! -d "$source_dir/.git" ]; then
  git clone https://github.com/libretro/nestopia.git "$source_dir"
fi
if ! git -C "$source_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
  git -C "$source_dir" fetch --depth 1 origin "$revision"
fi
if git -C "$source_dir" apply --reverse --check "$root/native/nestopia-powerglove/nestopia-powerglove.patch" 2>/dev/null; then
  git -C "$source_dir" apply --reverse "$root/native/nestopia-powerglove/nestopia-powerglove.patch"
fi
if ! git -C "$source_dir" diff --quiet || ! git -C "$source_dir" diff --cached --quiet; then
  printf '%s\n' "The isolated Nestopia source has unrelated tracked changes; use a new build directory." >&2
  exit 1
fi
git -C "$source_dir" checkout --detach "$revision"
git -C "$source_dir" apply --check "$root/native/nestopia-powerglove/nestopia-powerglove.patch"
git -C "$source_dir" apply "$root/native/nestopia-powerglove/nestopia-powerglove.patch"

if [ "${VIRTUALGLOVE_PREPARE_ONLY:-0}" = 1 ]; then
  printf '%s\n' "$source_dir"
  exit 0
fi

# The affected Nestopia implementation carries a 22-line upstream copyright
# and GPL header. Compare it directly with the pinned revision after patching;
# VirtualGlove changes belong below that header and in CHANGES.md.
header_check=$(mktemp -d)
trap 'rm -rf "$header_check"' EXIT HUP INT TERM
git -C "$source_dir" show "$revision:source/core/input/NstInpPowerGlove.cpp" \
  | sed -n '1,22p' > "$header_check/upstream"
sed -n '1,22p' "$source_dir/source/core/input/NstInpPowerGlove.cpp" \
  > "$header_check/patched"
if ! cmp -s "$header_check/upstream" "$header_check/patched"; then
  printf '%s\n' "The patch changed Nestopia's original copyright/license header." >&2
  exit 1
fi
# Diagnostics use a separate build directory and never replace the normal core.
if [ "${VIRTUALGLOVE_BUILD_DIAGNOSTICS:-0}" = 1 ]; then
  cp "$root/native/nestopia-powerglove/diagnostic_trace.h" "$source_dir/libretro/pgv_diagnostic_trace.h"
  python3 "$root/scripts/instrument-native-core.py" "$source_dir/libretro/libretro.cpp"
fi
build_platform=${VIRTUALGLOVE_LIBRETRO_PLATFORM:-}
if [ -n "$build_platform" ]; then
  make -C "$source_dir/libretro" -j"${JOBS:-2}" \
    CC="${CC:-cc}" CXX="${CXX:-c++}" AR="${AR:-ar}" \
    platform="$build_platform" >&2
else
  make -C "$source_dir/libretro" -j"${JOBS:-2}" >&2
fi

core=$(find "$source_dir/libretro" -maxdepth 1 -type f \( -name 'nestopia_libretro.so' -o -name 'nestopia_libretro.dylib' \) -print | head -n 1)
test -n "$core"
core_name=nestopia_powerglove_libretro
if [ "${VIRTUALGLOVE_BUILD_DIAGNOSTICS:-0}" = 1 ]; then
  core_name=nestopia_powerglove_diagnostic_libretro
fi
cp "$core" "$destination/$core_name.${core##*.}"
printf '%s\n' "$destination/$core_name.${core##*.}"
