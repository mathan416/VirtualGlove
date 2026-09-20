#!/bin/sh
# Project: VirtualGlove
# File: retropie/runcommand-onstart-virtualglove.sh
# Purpose: Forward RetroPie game-launch metadata to VirtualGlove without replacing existing cabinet hooks.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

# Call this from the cabinet's existing runcommand-onstart.sh, preserving its
# controller, RGB, and trackball setup. RetroPie supplies these four arguments.
# RetroPie may run a third-party joystick-selection hook before this one. That
# hook can replace or remove Player indexes in the system retroarch.cfg. Resolve
# Router outputs by their stable names after those hooks have finished, then
# update only our bounded block in the active system file. RetroArch's udev
# autoconfiguration supplies the button map. Native Nestopia (VirtualGlove) is
# deliberately excluded because it reads native-state.bin instead of a pad.
router_core=false
case "$2" in
    lr-fceumm|lr-nestopia)
        router_core=true
        ;;
esac
router_config="/opt/retropie/configs/$1/retroarch.cfg"
if $router_core && [ -f "$router_config" ] && [ ! -L "$router_config" ] \
        && [ -w "$router_config" ]; then
    router_block=$(mktemp /tmp/virtualglove-router.XXXXXX) || router_block=""
    router_output=false
    if [ -n "$router_block" ]; then
        : > "$router_block"
        for player in 1 2 3 4; do
            for joystick in /sys/class/input/js*; do
                [ -r "$joystick/device/name" ] || continue
                name=$(sed -n '1p' "$joystick/device/name")
                if [ "$name" = "VirtualGlove Merged Player $player" ]; then
                    index=${joystick##*js}
                    case "$index" in *[!0-9]*|'') continue ;; esac
                    if ! $router_output; then
                        printf '%s\n' '# VirtualGlove Controller Router' > "$router_block"
                    fi
                    printf 'input_player%s_joypad_index = "%s"\n' \
                        "$player" "$index" >> "$router_block"
                    router_output=true
                    break
                fi
            done
        done
        if $router_output; then
            printf '%s\n' '# End VirtualGlove Controller Router' >> "$router_block"
        fi
        router_temp=$(mktemp /tmp/virtualglove-retroarch.XXXXXX) || router_temp=""
        if [ -n "$router_temp" ]; then
            awk -v block="$router_block" '
                $0 == "# VirtualGlove Controller Router" { skipping=1; next }
                skipping && $0 == "# End VirtualGlove Controller Router" { skipping=0; next }
                !skipping && !inserted && /^#include[ \t]/ {
                    if ((getline line < block) > 0) {
                        print line
                        while ((getline line < block) > 0) print line
                        close(block); inserted=1
                    }
                }
                !skipping { print }
                END {
                    if (!inserted && (getline line < block) > 0) {
                        print line
                        while ((getline line < block) > 0) print line
                        close(block)
                    }
                }
            ' "$router_config" > "$router_temp" && \
                chmod --reference="$router_config" "$router_temp" && \
                cat "$router_temp" > "$router_config"
            rm -f "$router_temp"
        fi
        rm -f "$router_block"
    fi
fi
/opt/virtualglove/bin/virtualglove-retropie-hook start "$1" "$2" "$3" "$4"
exit 0
