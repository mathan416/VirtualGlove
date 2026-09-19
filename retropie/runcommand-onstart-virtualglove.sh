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
if [ -s /etc/virtualglove/controller-router.json ]; then
    /opt/virtualglove/bin/virtualglove-controller-router apply --platform retropie \
        --config /etc/virtualglove/controller-router.json || \
        echo "ACTION  Controller Router could not refresh; VirtualGlove input remains neutral." >&2
fi
/opt/virtualglove/bin/virtualglove-retropie-hook start "$1" "$2" "$3" "$4"
exit 0
