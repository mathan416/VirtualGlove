#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-launchbox-nestopia-powerglove.sh
# Purpose: Build the isolated Windows x86-64 Nestopia PowerGlove core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added the reproducible Windows x86-64 native-core build.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

revision=5a1cd378cb46ca9ccc2dd6f8b2b6a79ab986052e
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/build/launchbox-native"}
source_dir="$destination/source"
artifact_dir="$destination/x86_64"

if [ -n "${PYTHON:-}" ]; then
  python_cmd=$PYTHON
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=python3
elif command -v python >/dev/null 2>&1; then
  python_cmd=python
else
  printf '%s\n' "ERROR: Python 3 is required to verify and package the core." >&2
  exit 1
fi

mkdir -p "$destination" "$artifact_dir"
if [ ! -d "$source_dir/.git" ]; then
  git clone https://github.com/libretro/nestopia.git "$source_dir"
fi
if ! git -C "$source_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
  git -C "$source_dir" fetch --depth 1 origin "$revision"
fi
git -C "$source_dir" reset --hard "$revision"
git -C "$source_dir" clean -fdx
git -C "$source_dir" apply --check "$root/native/nestopia-powerglove/nestopia-powerglove.patch"
git -C "$source_dir" apply "$root/native/nestopia-powerglove/nestopia-powerglove.patch"
git -C "$source_dir" apply --check "$root/native/launchbox/nestopia-windows.patch"
git -C "$source_dir" apply "$root/native/launchbox/nestopia-windows.patch"

make_args=(platform=win)
if command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1; then
  make_args+=(CC=x86_64-w64-mingw32-gcc CXX=x86_64-w64-mingw32-g++)
fi
make -C "$source_dir/libretro" -j"${JOBS:-2}" "${make_args[@]}"
core="$source_dir/libretro/nestopia_libretro.dll"
test -f "$core"
output="$artifact_dir/nestopia_powerglove_libretro.dll"
cp "$core" "$output"
"$python_cmd" "$root/scripts/verify-launchbox-native-core.py" --core "$output"
if command -v x86_64-w64-mingw32-objdump >/dev/null 2>&1; then
  if x86_64-w64-mingw32-objdump -p "$output" |
      grep -Eiq 'DLL Name: (libgcc|libstdc\+\+|libwinpthread)'; then
    printf '%s\n' "ERROR: The LaunchBox core depends on an unbundled MinGW runtime DLL." >&2
    exit 1
  fi
fi
source_archive="$artifact_dir/nestopia-powerglove-source.tar.gz"
# Ship complete patched source without cross-compiler objects or a duplicate
# DLL. The reviewed DLL was copied and verified above.
make -C "$source_dir/libretro" "${make_args[@]}" clean
tar --exclude=.git -czf "$source_archive" -C "$source_dir" .

"$python_cmd" - "$destination/manifest.json" "$output" "$source_archive" "$revision" \
  "$root/native/nestopia-powerglove/nestopia-powerglove.patch" \
  "$root/native/launchbox/nestopia-windows.patch" <<'PY'
import hashlib, json, pathlib, sys
manifest, core, source, revision, base_patch, windows_patch = map(pathlib.Path, sys.argv[1:])
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
data = {
    "format": 1,
    "target": "launchbox-x86_64",
    "architecture": "x86_64",
    "nestopia_revision": str(revision),
    "base_patch_sha256": digest(base_patch),
    "windows_patch_sha256": digest(windows_patch),
    "core_sha256": digest(core),
    "core_size": core.stat().st_size,
    "source_sha256": digest(source),
    "source_size": source.stat().st_size,
}
manifest.write_text(json.dumps(data, indent=2) + "\n")
PY

printf '%s\n' "$output"
