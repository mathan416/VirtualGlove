#!/usr/bin/env bash
# Project: VirtualGlove
# File: scripts/build-batocera-nestopia-powerglove.sh
# Purpose: Cross-build and package the native Nestopia core with Batocera's exact target recipe.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added exact-target Batocera cross-compilation.
#   2026-09-16 - Build patched source inside Batocera's container and emit auditable artifacts.
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
destination=${3:-"$root/native/batocera"}
default_image=virtualglove/batocera-linux-build:43.1
image=${BATOCERA_BUILD_IMAGE:-$default_image}

mkdir -p "$destination"
destination=$(CDPATH= cd -- "$destination" && pwd)

[ -f "$batocera/Makefile" ] || { echo "Not a Batocera source tree: $batocera" >&2; exit 1; }
[ -f "$batocera/configs/batocera-$target.board" ] || {
  echo "Unsupported Batocera target: $target" >&2
  exit 1
}
case "$target" in
  bcm2835) platform=rpi1 ;;
  bcm2836) platform=rpi2 ;;
  bcm2837) platform=rpi3_64 ;;
  bcm2711) platform=rpi4_64 ;;
  bcm2712) platform=rpi5_64 ;;
  x86_64|rk3326|rk3399|rk3568|rk3588|s905|s905gen2|s905gen3|s922x|sm8250) platform=unix ;;
  *) echo "Unsupported or unverified Batocera native-core target: $target" >&2; exit 1 ;;
esac

version=$(sed -n 's/^BATOCERA_SYSTEM_VERSION = //p' \
  "$batocera/package/batocera/core/batocera-system/batocera-system.mk" | head -n 1)
case "$version" in
  43.1) ;;
  *) echo "Build from the validated Batocera 43.1 source; found: ${version:-unknown}" >&2; exit 1 ;;
esac
revision=$(git -C "$batocera" rev-parse HEAD 2>/dev/null || true)
if [ -z "$revision" ] && [ -f "$batocera/.virtualglove-build-revision" ]; then
  revision=$(sed -n '1p' "$batocera/.virtualglove-build-revision")
fi
[ -n "$revision" ] || {
  echo "Batocera revision is unavailable; use a Git checkout or .virtualglove-build-revision." >&2
  exit 1
}

if command -v gmake >/dev/null 2>&1; then
  batocera_make=gmake
else
  batocera_make=make
fi

# Prepare the pinned and patched GPL source inside Batocera's mounted tree so
# Buildroot can copy it into its target-specific output without altering the
# Batocera checkout or compiling a Linux toolchain directly on the host.
source_work="$batocera/.virtualglove-nestopia-powerglove"
source_dir=$(VIRTUALGLOVE_PREPARE_ONLY=1 \
  "$root/scripts/build-nestopia-powerglove.sh" "$source_work")
source_dir=$(CDPATH= cd -- "$source_dir" && pwd)
case "$source_dir" in
  "$batocera"/*) ;;
  *) echo "Prepared source must be inside the Batocera tree." >&2; exit 1 ;;
esac
container_source=/build/${source_dir#"$batocera"/}

# Generate the target defconfig on the host. The compilation itself stays in
# Batocera's official Linux build image. Named volumes avoid extremely slow
# compiler and chmod traffic across macOS/Linux file sharing and make retries
# resumable without mixing outputs between targets.
"$batocera_make" -C "$batocera" "$target-defconfig" >/dev/null
volume_prefix=virtualglove-batocera-${version//./-}
output_volume=$volume_prefix-$target-output
download_volume=$volume_prefix-downloads
ccache_volume=$volume_prefix-ccache
artifact_dir="$destination/$target/$version"
mkdir -p "$artifact_dir"

if ! docker image inspect "$image" >/dev/null 2>&1; then
  if [ "$image" = "$default_image" ]; then
    docker build -t "$image" - < "$batocera/Dockerfile" >/dev/null
  else
    docker pull "$image" >/dev/null
  fi
fi
image_id="$image@$(docker image inspect "$image" --format '{{.Id}}')"
uid=$(id -u)
gid=$(id -g)
docker run --rm --init \
  -e HOME=/tmp/virtualglove-home \
  -v "$batocera:/build:ro" \
  -v "$output_volume:/out" \
  -v "$download_volume:/downloads" \
  -v "$ccache_volume:/ccache" \
  -v "$artifact_dir:/artifacts" \
  -w /out \
  "$image" sh -eu -c '
    make O=/out BR2_EXTERNAL=/build BR2_DL_DIR=/downloads BR2_CCACHE_DIR=/ccache \
      -C /build/buildroot "batocera-'"$target"'_defconfig"
    make O=/out BR2_EXTERNAL=/build BR2_DL_DIR=/downloads BR2_CCACHE_DIR=/ccache \
      -C /build/buildroot toolchain
    work=/out/build/virtualglove-nestopia-powerglove
    rm -rf "$work"
    mkdir -p "$work"
    tar --exclude=.git -C '"$container_source"' -cf - . | tar -C "$work" -xf -
    cxx=$(find /out/host/bin -maxdepth 1 \( -type f -o -type l \) -name "*-g++" | head -n 1)
    test -n "$cxx"
    prefix=${cxx%-g++}
    make -C "$work/libretro" -j"$(nproc)" \
      CC="$prefix-gcc" CXX="$cxx" AR="$prefix-ar" platform='"$platform"'
    core="$work/libretro/nestopia_libretro.so"
    test -f "$core"
    install -m 0644 "$core" /artifacts/nestopia_powerglove_libretro.so
    chown '"$uid:$gid"' /artifacts/nestopia_powerglove_libretro.so
  '

output="$artifact_dir/nestopia_powerglove_libretro.so"
[ -f "$output" ] || { echo "Batocera build did not produce $output" >&2; exit 1; }
source_archive="$artifact_dir/nestopia-powerglove-source.tar.gz"
COPYFILE_DISABLE=1 tar --exclude=.git -czf "$source_archive" -C "$source_dir" .
nestopia_revision=$(git -C "$source_dir" rev-parse HEAD)
manifest="$destination/manifest.json"
python3 - "$output" "$manifest" "$target" "$version" "$revision" \
  "$nestopia_revision" "$root/native/nestopia-powerglove/nestopia-powerglove.patch" \
  "$source_archive" "$image_id" <<'PY'
import hashlib, json, pathlib, struct, sys

p = pathlib.Path(sys.argv[1])
raw = p.read_bytes()
d = raw[:64]
if d[:4] != b"\x7fELF" or d[4] not in (1, 2) or d[5] != 1:
    raise SystemExit("Batocera core is not a supported little-endian ELF file")
elf_class = {1: 32, 2: 64}[d[4]]
machine = struct.unpack("<H", d[18:20])[0]
try:
    elf_machine = {40: "arm", 62: "x86_64", 183: "aarch64"}[machine]
except KeyError:
    raise SystemExit("Batocera core has an unsupported ELF machine") from None
target, version = sys.argv[3:5]
expected_elf = {
    "bcm2835": (32, "arm"),
    "bcm2836": (32, "arm"),
    "bcm2837": (64, "aarch64"),
    "bcm2711": (64, "aarch64"),
    "bcm2712": (64, "aarch64"),
    "x86_64": (64, "x86_64"),
    "rk3326": (64, "aarch64"),
    "rk3399": (64, "aarch64"),
    "rk3568": (64, "aarch64"),
    "rk3588": (64, "aarch64"),
    "s905": (64, "aarch64"),
    "s905gen2": (64, "aarch64"),
    "s905gen3": (64, "aarch64"),
    "s922x": (64, "aarch64"),
    "sm8250": (64, "aarch64"),
}[target]
if (elf_class, elf_machine) != expected_elf:
    raise SystemExit("Batocera core ELF identity does not match its target")
patch = pathlib.Path(sys.argv[7]).read_bytes()
source = pathlib.Path(sys.argv[8]).read_bytes()
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
    "batocera_version": version,
    "batocera_revision": sys.argv[5],
    "build_image": sys.argv[9],
    "nestopia_revision": sys.argv[6],
    "patch_sha256": hashlib.sha256(patch).hexdigest(),
}
manifest = pathlib.Path(sys.argv[2])
data = json.loads(manifest.read_text()) if manifest.exists() else {"format": 2, "cores": {}}
if data.get("format") != 2 or not isinstance(data.get("cores"), dict):
    raise SystemExit("Refusing to merge into an unsupported Batocera manifest")
data["cores"].setdefault(target, {})[version] = entry
temporary = manifest.with_suffix(".new")
temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
temporary.replace(manifest)
PY
printf '%s\n' "$output"
printf '%s\n' "$source_archive"
printf '%s\n' "$manifest"
