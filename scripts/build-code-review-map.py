#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-code-review-map.py
# Purpose: Regenerate the private file hierarchy and code-review navigation map.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Included nonignored new files before their first commit.
#   2026-09-18 - Added deterministic 0.5.0 architecture and source inventory generation.
# Full history: docs/CHANGELOG.md and Git history.

"""Build docs/CODE_REVIEW_MAP.txt from the current Git-visible checkout."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs" / "CODE_REVIEW_MAP.txt"


def git(*arguments: str) -> str:
    """Return one bounded Git query as text."""
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def visible_files() -> list[str]:
    """Return tracked and nonignored new files visible in this checkout."""
    result = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = {path for path in result.split("\0") if path and (ROOT / path).is_file()}
    paths.add("scripts/build-code-review-map.py")
    return sorted(paths)


def tree(paths: list[str]) -> str:
    """Render a deterministic ASCII tree without requiring an external utility."""
    root: dict[str, dict] = {}
    for path in paths:
        node = root
        for part in Path(path).parts:
            node = node.setdefault(part, {})

    lines = ["."]

    def visit(node: dict[str, dict], prefix: str) -> None:
        """Append one sorted directory level and recursively render children."""
        entries = sorted(node.items(), key=lambda item: (not bool(item[1]), item[0].lower()))
        for index, (name, children) in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(f"{prefix}{'`-- ' if last else '|-- '}{name}")
            if children:
                visit(children, prefix + ("    " if last else "|   "))

    visit(root, "")
    return "\n".join(lines)


def main(*, check: bool = False) -> int:
    """Regenerate the complete review map."""
    files = visible_files()
    project_text = (ROOT / "pyproject.toml").read_text()
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', project_text, re.MULTILINE)
    if version_match is None:
        raise ValueError("pyproject.toml does not declare the project version")
    version = version_match.group(1)
    tests = [path for path in files if path.startswith("tests/test_") and path.endswith(".py")]
    browser = [path for path in files if path.startswith("tests/browser_")]
    harnesses = [path for path in files if path.startswith("tests/") and "harness." in path]

    preface = f"""VIRTUALGLOVE - FILE HIERARCHY AND CODE REVIEW MAP
===================================================
Source: {ROOT}
Project version: {version}
Git-visible files: {len(files)}
Python test modules: {len(tests)}
Standalone browser checks: {len(browser)}
JavaScript browser harnesses: {len(harnesses)}

This private map is a generated reading aid, not a completed code or security
audit. Regenerate or verify it with:

    python3 scripts/build-code-review-map.py
    python3 scripts/build-code-review-map.py --check

CURRENT SYSTEM
--------------
VirtualGlove runs camera-based hand recognition on an Arduino UNO Q. The
persistent supervisor in python/main.py owns the worker lifecycle and the
always-available web application. The worker keeps only the newest camera
frame, applies the selected player's calibration and gesture settings, and
sends signed protocol-v2 controller state. Controller output remains neutral
when disabled, unpaired, uncalibrated, timed out, or in safe practice modes.

The supported console integrations are deliberately different:

* RetroPie receives VirtualGlove as a separate Linux input device by default.
  Optional Controller Router can combine configured physical controllers and
  VirtualGlove into enabled Players 1-4.
* Recalbox and Batocera use Controller Router for enabled merged Players 1-4,
  preserving EmulationStation mappings, the physical Player 1 hotkey, and
  unrelated settings while carrying physical assignments through Libretro.
* LaunchBox keeps the physical XInput controller and real keyboard available,
  while managed FCEUmm launches receive VirtualGlove through loopback Network
  RetroPad. Super Glove Ball uses the native Nestopia state path.

Programs 1-14, Programs A-I, Bad Street Brawler, Super Glove Ball, and Gestures
off share the same player, pairing, registry, rapid-fire, and safety model.
FCEUmm handles ordinary NES mappings. Packaged Nestopia PowerGlove cores provide
native Super Glove Ball behaviour on supported console architectures.

REVIEW ORDER
------------
1. README.md and docs/ARCHITECTURE.md for supported behaviour and boundaries.
2. python/main.py and src/virtualglove/control_server.py for supervision,
   persistence, web/API ownership, and controller arming.
3. tracker.py -> gesture.py -> vision_app.py for camera-to-controller state.
4. controller_protocol.py -> transport.py -> receiver.py for authenticated
   delivery, replay protection, timeout release, and output backends.
5. Platform launch/install paths below, followed by their matching tests.
6. scripts/application-payload.py, scripts/install-package.py, and
   scripts/installation-manifest.py before changing upgrade behaviour.

RUNTIME AND PLATFORM MAP
------------------------
Controller and web application
  python/main.py                         App Lab supervisor and worker restart
  src/virtualglove/control_server.py     persistent HTTP/HTTPS API and config
  src/virtualglove/vision_app.py         active camera/gesture worker
  src/virtualglove/tracker.py            MediaPipe tracking and recovery
  src/virtualglove/gesture.py            profile mappings and safe releases
  src/virtualglove/players.py            versioned per-player records
  src/virtualglove/tuning.py             calibration and tuning transactions
  src/virtualglove/*_web.py              Dashboard, Setup, Academy, games, tuning
  uno-q/                                 host services and recovery helpers
  sketch/                                UNO Q matrix firmware

Shared console transport
  src/virtualglove/controller_protocol.py signed protocol-v2 envelope
  src/virtualglove/transport.py           newest-state UDP sender
  src/virtualglove/receiver.py            authenticated receiver and release
  src/virtualglove/native_state.py        native core shared-state record
  src/virtualglove/game_registry.py       exact ROM registration and overrides
  src/virtualglove/pairing.py             code/SSH provisioning contracts

RetroPie
  retropie/                               services, hooks, and RetroArch config
  src/virtualglove/retropie_hook.py       registered-game launch selection
  src/virtualglove/profile_control.py     local profile requests

Controller Router on RetroPie, Recalbox, and Batocera
  recalbox/ and batocera/                 persistent platform launch assets
  src/virtualglove/controller_router.py   Players 1-4 routing and management
  src/virtualglove/merged_gamepad.py      shared input/mapping primitives
  scripts/install-recalbox.sh             Recalbox installation and upgrade
  scripts/install-batocera.sh             Batocera installation and upgrade
  native/recalbox and native/batocera     verified multi-architecture cores

LaunchBox
  launchbox/                              Windows installer and append configs
  src/virtualglove/launchbox_hook.py       per-game route and core selection
  src/virtualglove/launchbox_runtime.py    supervised Windows input runtime
  src/virtualglove/retroarch_remote.py     loopback Network RetroPad output
  src/virtualglove/retroarch_hotkeys.py    keyboard fallback collision audit
  native/launchbox/                        verified Windows Nestopia core

Native emulation and engineering
  native/nestopia-powerglove/             maintained libretro core patch
  native/powerglove-dot/                   diagnostic native input target
  scripts/benchmark-*.py                   bounded engineering comparisons
  scripts/*latency*.py                     private finite latency evidence
  docs/ENGINEERING_TOOLKIT.md              supported engineering workflows

DATA AND SECURITY BOUNDARIES
----------------------------
Preserve data/device.json, player tuning and calibration, controller intent,
game registries, pairing credentials, ROMs, saves, and platform controller
configuration during every update. Public status must never expose pairing
tokens or private key material. Pairing requires a short-lived physical UNO Q
confirmation. Network controller packets require signed protocol v2 and replay
protection. Tracking loss, receiver timeout, process exit, and install/upgrade
must release all synthesized input.

The ignored data/ directory contains private engineering recordings and is not
a release asset. Generated installers live under output/install; build products
live under build; both are reproducible and ignored. Published documentation
PDFs under output/pdf and verified native core artifacts under native are
tracked release inputs and must not be treated as disposable caches.

TEST MAP
--------
Normal Python discovery currently contains {len(tests)} test modules. JavaScript
harnesses are invoked by their Python wrappers. The browser_*.py files are
standalone physical/browser acceptance checks and are not discovered by
unittest. Platform-specific hardware acceptance remains necessary after the
automated suite.

Retain tests that appear historical when they protect a current boundary:

* 0.4.2 -> 0.5.0 namespace and installer upgrades;
* rejection of protocol v1 and retired command-line options;
* removal of old PowerGlove runtime/service files;
* unsupported player/import formats remaining untouched;
* internal directional-search behaviour (the old device setting is retired,
  but the bounded tracking algorithm is active).

Primary validation commands are maintained in docs/CONTRIBUTING.md and CI in
.github/workflows. The local supported runner is:

    python3 scripts/run-tests.py --setup
    python3 scripts/run-tests.py

Release validation additionally covers source/documentation audits, JavaScript
syntax and browser harnesses, installer/package verification, native manifests,
PDF rendering, UNO Q behaviour, and each affected console platform.

CONSERVATIVE RC1 CLEANUP AUDIT
------------------------------
No complete runtime module is confirmed dead at the v0.5.0-rc.1 boundary.
Several paths can look historical but still carry upgrade, rollback, packaging,
or active platform responsibilities and must remain through this release:

* the v6 player reader, ready_progress removal, and retired Ready marker cleanup
  migrate the oldest supported v0.4.2 installation without keeping that feature;
* retired Python-package and old service-name cleanup removes names released
  before v0.5.0 and is not an endorsement of those names for new installations;
* merged_gamepad.py is shared by Controller Router and the standard RetroPie
  backend even though the old cabinet merger service is retired;
* Controller Router migration and rollback primitives protect already tested
  Recalbox, Batocera, and cabinet RetroPie installations;
* native core names and Power Glove hardware terms describe active compatibility
  interfaces rather than obsolete VirtualGlove branding.

Revisit these compatibility paths for v0.5.1 only after the v0.5.0 upgrade
window has shipped and its rollback evidence has been archived. Until then,
removing them would trade small source savings for avoidable release risk.

DOCUMENTATION AND DELIVERY
--------------------------
Maintained Markdown is rendered into the built-in Help pages and the tracked PDF
editions under output/pdf. Preserve the glove design language and intentional
extra-digit artwork used by Pixel Pal's Extra-Digit Hunt. Documentation images
must use simulated, non-secret fixtures. scripts/application-payload.py defines
the public Controller payload; installer manifests preserve user-owned data and
back up modified managed files before replacement.

The public static website is tracked under website/, reads bounded release facts
from config/release.json, and produces a manual-upload ZIP. Enclosure print-file
ownership is recorded in hardware/enclosures/enclosure-files.json; its builder
creates separate UNO Q Case, Dock V1, and Dock V2 archives without changing the
stable individual-download paths.

COMPLETE GIT-VISIBLE INVENTORY
------------------------------
{len(files)} tracked or non-ignored files are present in this checkout. Ignored
virtual environments, private data, generated installers, and build products
are intentionally omitted.

{tree(files)}
"""
    if check:
        if not DESTINATION.exists() or DESTINATION.read_text() != preface:
            print("FAIL  docs/CODE_REVIEW_MAP.txt is stale; regenerate it")
            return 1
        print(f"PASS  {DESTINATION.relative_to(ROOT)} matches {len(files)} files.")
        return 0
    DESTINATION.write_text(preface)
    print(
        f"PASS  Wrote {DESTINATION.relative_to(ROOT)}: {len(files)} files, "
        f"{len(tests)} Python test modules."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing when the map is stale")
    raise SystemExit(main(check=parser.parse_args().check))
