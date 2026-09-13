#!/bin/sh
# Project: VirtualGlove
# File: retropie/runcommand-onend-virtualglove.sh
# Purpose: Tell VirtualGlove that a RetroPie game ended without replacing existing cabinet hooks.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

# Call this from the cabinet's existing runcommand-onend.sh.
/opt/virtualglove/bin/virtualglove-retropie-hook end
exit 0
