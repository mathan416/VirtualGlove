# Project: VirtualGlove
# File: src/virtualglove/merged_gamepad.py
# Purpose: Compatibility path for the shared Controller Router merged-gamepad module.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-11-16 - Re-export router_shared.merged_gamepad instead of keeping a diverged copy.
#   2026-09-19 - Distinguished multiple gamepad interfaces exposed by one USB board.
#   2026-09-16 - Added Recalbox/Batocera merged Player 1 input.
# Full history: docs/CHANGELOG.md and Git history.

"""Keep the virtualglove.merged_gamepad import path; the implementation is shared."""

from __future__ import annotations

from router_shared import merged_gamepad as _core

# Existing receiver, installer, and cabinet callers use this module path.
# Export the shared module's API so fixes there reach VirtualGlove too.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

if __name__ == "__main__":
    raise SystemExit(_core.main())
