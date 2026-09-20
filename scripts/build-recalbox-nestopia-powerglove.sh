#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-recalbox-nestopia-powerglove.sh
# Purpose: Build the native Nestopia core with Recalbox's exact target recipe.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added exact-target Recalbox native-core builds.
# Full history: docs/CHANGELOG.md and Git history.
set -eu

usage() {
  echo "Usage: $0 RECALBOX_SOURCE TARGET [DESTINATION]" >&2
  echo "Example: $0 /path/to/recalbox rpizero2" >&2
  exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
recalbox=$(CDPATH= cd -- "$1" && pwd)
target=$2

[ -x "$recalbox/scripts/linux/recaldocker.sh" ] || {
  echo "Not a Recalbox source tree: $recalbox" >&2
  exit 1
}
[ -f "$recalbox/configs/recalbox-$target"_defconfig ] || {
  echo "Unsupported Recalbox target: $target" >&2
  exit 1
}
case "$target" in
  rpizero2|rpi3|rpi4_64|rpi5_64|rg353x|odroidgo2|x86_64) ;;
  *) echo "Unsupported Recalbox native-core target: $target" >&2; exit 1 ;;
esac

recalbox_version=$(git -C "$recalbox" describe --tags --exact-match 2>/dev/null || true)
case "$recalbox_version" in
  10.*) ;;
  *) echo "Build from an exact Recalbox 10.x release tag; found: ${recalbox_version:-untagged}" >&2; exit 1 ;;
esac
destination=${3:-"$root/build/recalbox-native"}

mkdir -p "$destination"
work="$destination/.work-$target-$recalbox_version"
source_dir=$(VIRTUALGLOVE_PREPARE_ONLY=1 \
  "$root/scripts/build-nestopia-powerglove.sh" "$work")
source_dir=$(CDPATH= cd -- "$source_dir" && pwd)

# Recalbox's own package recipe supplies its Buildroot compiler, sysroot,
# optimisation flags, sysroot, and target-specific libretro platform. An
# override source keeps the Recalbox checkout itself unmodified.
(
  cd "$recalbox"
  # Recalbox 10.1's development image installs an i386 host package and is an
  # amd64 builder even when Docker itself runs on Apple Silicon or ARM Linux.
  # Only the builder is emulated; Buildroot still emits the selected ARM core.
  docker_arch=$(docker info --format '{{.Architecture}}')
  case "$docker_arch" in
    x86_64|amd64) ;;
    *)
      export DOCKER_DEFAULT_PLATFORM=linux/amd64
      docker pull --platform linux/amd64 ubuntu:22.04 >/dev/null
      ;;
  esac
  # Buildroot output is target-specific. A clean output prevents stale package
  # stamps and sysroot files from one Recalbox target contaminating another.
  ARCH="$target" scripts/linux/recaldocker.sh make clean
  ARCH="$target" scripts/linux/recaldocker.sh \
    make "recalbox-$target"_defconfig
  ARCH="$target" scripts/linux/recaldocker.sh \
    make LIBRETRO_NESTOPIA_OVERRIDE_SRCDIR="$source_dir" \
    libretro-nestopia-dirclean libretro-nestopia
)

core="$recalbox/output/build/libretro-nestopia-custom/libretro/nestopia_libretro.so"
[ -f "$core" ] || { echo "Recalbox build did not produce $core." >&2; exit 1; }
artifact_dir="$destination/$target/$recalbox_version"
mkdir -p "$artifact_dir"
output="$artifact_dir/nestopia_powerglove_libretro.so"
cp "$core" "$output"
manifest="$destination/manifest.json"
source_archive="$artifact_dir/nestopia-powerglove-source.tar.gz"
COPYFILE_DISABLE=1 tar --exclude=.git -czf "$source_archive" -C "$source_dir" .
recalbox_revision=$(git -C "$recalbox" rev-parse HEAD)
nestopia_revision=$(git -C "$source_dir" rev-parse HEAD)
python3 - "$output" "$manifest" "$target" "$recalbox_version" "$recalbox_revision" \
  "$nestopia_revision" "$root/native/nestopia-powerglove/nestopia-powerglove.patch" \
  "$source_archive" <<'PY'
import hashlib, json, pathlib, struct, sys
p = pathlib.Path(sys.argv[1])
raw = p.read_bytes()
d = raw[:64]
if d[:4] != b"\x7fELF" or d[4] not in (1, 2) or d[5] != 1:
    raise SystemExit("Recalbox core is not a supported little-endian ELF file")
elf_class = {1: 32, 2: 64}[d[4]]
machine = struct.unpack("<H", d[18:20])[0]
try:
    elf_machine = {40: "arm", 62: "x86_64", 183: "aarch64"}[machine]
except KeyError:
    raise SystemExit("Recalbox core has an unsupported ELF machine") from None
patch = pathlib.Path(sys.argv[7]).read_bytes()
source = pathlib.Path(sys.argv[8]).read_bytes()
target, version = sys.argv[3:5]
expected_elf = {
    "rpizero2": (32, "arm"),
    "rpi3": (32, "arm"),
    "rpi4_64": (64, "aarch64"),
    "rpi5_64": (64, "aarch64"),
    "rg353x": (64, "aarch64"),
    "odroidgo2": (64, "aarch64"),
    "x86_64": (64, "x86_64"),
}[target]
if (elf_class, elf_machine) != expected_elf:
    raise SystemExit("Recalbox core ELF identity does not match its target")
relative = target + "/" + version + "/"
entry = {
    "file": relative + "nestopia_powerglove_libretro.so",
    "sha256": hashlib.sha256(raw).hexdigest(),
    "size": len(raw),
    "elf_class": elf_class,
    "elf_machine": elf_machine,
    "source_file": relative + "nestopia-powerglove-source.tar.gz",
    "source_sha256": hashlib.sha256(source).hexdigest(),
    "source_size": len(source),
    "recalbox_version": version,
    "recalbox_revision": sys.argv[5],
    "nestopia_revision": sys.argv[6],
    "patch_sha256": hashlib.sha256(patch).hexdigest(),
}
manifest = pathlib.Path(sys.argv[2])
data = json.loads(manifest.read_text()) if manifest.exists() else {"format": 2, "cores": {}}
if data.get("format") != 2 or not isinstance(data.get("cores"), dict):
    raise SystemExit("Refusing to merge into an unsupported Recalbox manifest")
data["cores"].setdefault(target, {})[version] = entry
temporary = manifest.with_suffix(".new")
temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
temporary.replace(manifest)
PY
printf '%s\n' "$output"
printf '%s\n' "$source_archive"
printf '%s\n' "$manifest"
