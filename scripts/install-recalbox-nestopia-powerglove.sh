#!/bin/sh
# Project: VirtualGlove
# File: scripts/install-recalbox-nestopia-powerglove.sh
# Purpose: Validate and install one Recalbox-targeted native Nestopia core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added target-side Recalbox core validation and installation.
# Full history: docs/CHANGELOG.md and Git history.

set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "Usage: $0 CORE [SUPER_GLOVE_BALL_ROM]" >&2
    exit 2
}
[ "$(id -u)" -eq 0 ] || { echo "Run this command as Recalbox root." >&2; exit 1; }
[ -f /recalbox/recalbox.version ] || { echo "This target is not Recalbox." >&2; exit 1; }
pgrep -x retroarch >/dev/null 2>&1 && { echo "Close the running game before installing the core." >&2; exit 1; }

source_core=$1
[ -f "$source_core" ] && [ ! -L "$source_core" ] || { echo "Core is missing or symbolic: $source_core" >&2; exit 1; }
app=/recalbox/share/system/virtualglove
[ -f "$app/recalbox/virtualglove-core-mount" ] || { echo "Install VirtualGlove for Recalbox first." >&2; exit 1; }

# Load-check on the target before making the core persistent or visible.
arch=$(cat /recalbox/recalbox.arch)
version=$(cat /recalbox/recalbox.version)
manifest="$app/native/recalbox/manifest.json"
target=$(python3 "$app/scripts/verify-recalbox-native-core.py" \
    --manifest "$manifest" --arch "$arch" --version "$version" --resolve-core)
python3 "$app/scripts/verify-recalbox-native-core.py" \
    --manifest "$manifest" --core "$source_core" --arch "$arch" \
    --version "$version" --load
mkdir -p "$(dirname "$target")"
temporary="$target.new.$$"
trap 'rm -f "$temporary"' EXIT HUP INT TERM
cp "$source_core" "$temporary"
chmod 0644 "$temporary"
mv "$temporary" "$target"
trap - EXIT HUP INT TERM

sh "$app/recalbox/virtualglove-core-mount" start
sh "$app/recalbox/virtualglove-core-mount" status
if [ "$#" -eq 2 ]; then
    python3 "$app/scripts/configure-recalbox-super-glove-ball-core.py" \
        --rom "$2" --mode native --apply
fi
echo "PASS  Nestopia (VirtualGlove) is installed separately from stock Nestopia."
