#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/stamp-build-version.py
# Purpose: Stamp release and source-branch metadata into an exported application.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Stamp exact commits, candidate versions, and expected firmware identity.
#   2026-09-04 - Derive the displayed version from release and build metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Write the build identity before Git metadata is removed from a package."""

import argparse
import json
import runpy
from pathlib import Path


def main():
    """Generate build metadata at the requested package-relative destination."""
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    versioning = runpy.run_path(str(root / "src/virtualglove/versioning.py"))
    identity = versioning["exact_build_identity"](root)
    if identity["branch"] == "unknown":
        raise SystemExit("Cannot identify source branch; build from a Git checkout or a named CI branch.")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(json.dumps(identity, indent=2) + "\n")
    print("Build version: " + versioning["display_version"](identity))


if __name__ == "__main__":
    main()
