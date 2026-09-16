#!/bin/sh
# Project: VirtualGlove
# File: scripts/install-batocera-nestopia-powerglove.sh
# Purpose: Validate and install one Batocera-targeted native Nestopia core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added load-checked Batocera native-core installation.
# Full history: docs/CHANGELOG.md and Git history.

set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "Usage: $0 CORE [SUPER_GLOVE_BALL_ROM]" >&2
    exit 2
}
[ "$(id -u)" -eq 0 ] || { echo "Run this command as Batocera's root user." >&2; exit 1; }
[ -f /usr/share/batocera/batocera.version ] || { echo "This target is not Batocera." >&2; exit 1; }
pgrep -x retroarch >/dev/null 2>&1 && { echo "Close the running game before installing the core." >&2; exit 1; }

source_core=$1
[ -f "$source_core" ] && [ ! -L "$source_core" ] || { echo "Core is missing or symbolic: $source_core" >&2; exit 1; }
app=/userdata/system/virtualglove
[ -x "$app/batocera/virtualglove-core-mount" ] || { echo "Install VirtualGlove for Batocera first." >&2; exit 1; }

# Loading the shared object proves that its CPU, libc and dynamic dependencies
# match this exact Batocera image before it can affect the frontend core view.
python3 - "$source_core" <<'PY'
import ctypes, pathlib, sys
path = pathlib.Path(sys.argv[1]).resolve()
library = ctypes.CDLL(str(path))
for symbol in ("retro_api_version", "retro_get_system_info", "retro_init"):
    getattr(library, symbol)
if library.retro_api_version() != 1:
    raise SystemExit("Core does not expose the supported libretro API")
class SystemInfo(ctypes.Structure):
    _fields_ = [("library_name", ctypes.c_char_p), ("library_version", ctypes.c_char_p),
                ("valid_extensions", ctypes.c_char_p), ("need_fullpath", ctypes.c_bool),
                ("block_extract", ctypes.c_bool)]
info = SystemInfo()
library.retro_get_system_info(ctypes.byref(info))
if info.library_name != b"Nestopia PowerGlove":
    raise SystemExit("Core identity is not Nestopia PowerGlove")
PY

target="$app/native/batocera/runtime/nestopia_powerglove_libretro.so"
mkdir -p "$(dirname "$target")"
temporary="$target.new.$$"
trap 'rm -f "$temporary"' EXIT HUP INT TERM
cp "$source_core" "$temporary"
chmod 0644 "$temporary"
mv "$temporary" "$target"
trap - EXIT HUP INT TERM

"$app/batocera/virtualglove-core-mount" restart
"$app/batocera/virtualglove-core-mount" status
if [ "$#" -eq 2 ]; then
    python3 "$app/scripts/configure-batocera-super-glove-ball-core.py" \
        --rom "$2" --mode native --apply
fi
echo "PASS  Nestopia (VirtualGlove) is installed separately from stock Nestopia."
