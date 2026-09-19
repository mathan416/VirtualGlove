#!/usr/bin/env python3
# Project: VirtualGlove
# File: retropie/arcade-cabinet-merger/propose-controller-router.py
# Purpose: Build, but never apply, the development cabinet's Router proposal.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added non-mutating cabinet migration proposal.
# Full history: docs/CHANGELOG.md and Git history.

"""Build the known cabinet's Controller Router proposal without applying it."""

import argparse
import json
from pathlib import Path

from virtualglove.controller_router import FORMAT, validate_config
from virtualglove.merged_gamepad import controller_candidates

IPAC = "Ultimarc I-PAC Ultimate I/O"
EIGHTBITDO = {
    "8BitDo 8BitDo Ultimate wireless Controller for PC",
    "8BitDo Ultimate Wireless / Pro 2 Wired Controller",
}


def proposal(es_inputs: Path) -> dict:
    """Map known I-PAC and 8BitDo sources into the cabinet's two players."""
    candidates = controller_candidates(es_inputs)
    ipacs = sorted((item for item in candidates if item["name"] == IPAC),
                   key=lambda item: (item.get("phys", ""), item["id"]))
    pads = sorted((item for item in candidates if item["name"] in EIGHTBITDO),
                  key=lambda item: (item.get("phys", ""), item["id"]))
    players = []
    for player in (1, 2):
        sources = []
        if len(ipacs) >= player: sources.append(ipacs[player - 1])
        if len(pads) >= player: sources.append(pads[player - 1])
        if sources: players.append({"player": player, "sources": sources})
    if not players:
        raise ValueError("No known cabinet I-PAC or 8BitDo sources are configured and connected.")
    return validate_config({"format": FORMAT, "platform": "retropie",
                            "players": players, "virtualglove_player": 1})


def main() -> int:
    """Write one new proposal file and refuse overwrite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--es-inputs", type=Path,
                        default=Path("/opt/retropie/configs/all/emulationstation/es_input.cfg"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = proposal(args.es_inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("x") as stream:
            stream.write(json.dumps(data, indent=2) + "\n")
    except FileExistsError:
        raise SystemExit("Refusing to overwrite an existing proposal.") from None
    print("Proposal written; no service or RetroArch setting was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
