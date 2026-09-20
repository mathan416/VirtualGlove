#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-installer-scripts.py
# Purpose: Generate standalone installer entrypoints from one maintained template.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Removed independently maintained bootstrap copies.
# Full history: docs/CHANGELOG.md and Git history.

"""Generate standalone release installers, or check they match their shared source."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(machine):
    """Expand only fixed installer identity and installed paths."""
    setup_root = {"uno-q": "/home/arduino/ArduinoApps/virtualglove",
                  "retropie": "/opt/virtualglove-src",
                  "recalbox": "/recalbox/share/system/virtualglove",
                  "batocera": "/userdata/system/virtualglove"}[machine]
    setup = setup_root + "/scripts/setup-machine.py"
    archive = "VirtualGlove-" + {"uno-q": "Uno-Q", "retropie": "RetroPie",
                                  "recalbox": "Recalbox",
                                  "batocera": "Batocera"}[machine] + ".zip"
    return (ROOT / "scripts/templates/install.sh.in").read_text().replace(
        "@@MACHINE@@", machine).replace("@@SETUP@@", setup).replace("@@ARCHIVE@@", archive)


def main():
    """Write generated scripts or fail if a separately edited copy has drifted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for machine in ("uno-q", "retropie", "recalbox", "batocera"):
        path = ROOT / ("scripts/install-" + machine + ".sh")
        text = render(machine)
        if args.check:
            if not path.exists() or path.read_text() != text:
                raise SystemExit("Regenerate installer scripts: " + str(path))
        else:
            path.write_text(text)
            path.chmod(0o755)


if __name__ == "__main__":
    main()
