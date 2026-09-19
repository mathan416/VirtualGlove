#!/usr/bin/env python3
# Project: VirtualGlove
# File: retropie/arcade-cabinet-merger/cabinet-controller-router-migration.py
# Purpose: Validate, apply, or roll back the development cabinet Router migration.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added receipt-gated cabinet migration and one-command rollback.
# Full history: docs/CHANGELOG.md and Git history.

"""Migrate the proven cabinet merger only after a successful Router preflight."""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from virtualglove.controller_router import (
    ControllerRouterDevice, atomic_write, enabled_players, fceumm_running,
    load_config, output_indexes, revision, test_activity,
)

ROUTER_CONFIG = Path("/etc/virtualglove/controller-router.json")
FCEUMM_CONFIG = Path("/opt/retropie/configs/all/retroarch/config/FCEUmm/FCEUmm.cfg")
GLOBAL_CONFIG = Path("/opt/retropie/configs/nes/retroarchcustom.cfg")
RECEIPT = Path("/etc/virtualglove/controller-router-cabinet-check.json")
STATE = Path("/etc/virtualglove/controller-router-cabinet-migration.json")
OLD_SERVICE = "arcade-gamepad-merger.service"
ROUTER_SERVICE = "virtualglove-controller-router.service"


def _service_state(name: str, action: str) -> bool:
    """Read one bounded systemd state without parsing human output."""
    return subprocess.run(("systemctl", action, "--quiet", name),
                          check=False).returncode == 0


def _run(*command: str) -> None:
    """Run one fixed administrative command."""
    subprocess.run(command, check=True)


def _saved_text(path: Path) -> str | None:
    """Read a managed text file or record that it did not exist."""
    return path.read_text() if path.is_file() and not path.is_symlink() else None


def _restore(path: Path, text: str | None, mode: int = 0o600) -> None:
    """Restore one recorded file state exactly."""
    if text is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, text, mode)


def check(proposal_path: Path, watch_ms: int) -> None:
    """Validate identities, live physical input, and temporary uinput outputs."""
    if os.geteuid() != 0:
        raise ValueError("Run cabinet validation as root.")
    if fceumm_running():
        raise ValueError("Close the running FCEUmm game before validation.")
    proposal = load_config(proposal_path)
    if proposal["platform"] != "retropie":
        raise ValueError("The cabinet proposal must target RetroPie.")
    assigned = {source["id"] for entry in proposal["players"] for source in entry["sources"]}
    es_inputs = Path("/opt/retropie/configs/all/emulationstation/es_input.cfg")
    activity = test_activity(es_inputs, watch_ms)
    missing_activity = sorted(assigned - set(activity))
    if missing_activity:
        raise ValueError("Press a control on every proposed physical source during validation.")
    runtime = Path("/run/virtualglove")
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="router-cabinet-check-", dir=runtime) as directory:
        temporary = Path(directory)
        config = temporary / "controller-router.json"
        atomic_write(config, json.dumps(proposal, indent=2) + "\n")
        device = ControllerRouterDevice(
            config, temporary / "FCEUmm.cfg", temporary / "router.sock",
            global_config=GLOBAL_CONFIG)
        try:
            if len(output_indexes(enabled_players(proposal))) != len(enabled_players(proposal)):
                raise ValueError("Not every proposed merged player output appeared.")
        finally:
            device.close()
    atomic_write(RECEIPT, json.dumps({"format": 1, "revision": revision(proposal),
        "checked_at": int(time.time()), "physical_sources": sorted(assigned)}, indent=2) + "\n")
    print("PASS  Cabinet sources and temporary Controller Router outputs validated.")


def rollback() -> None:
    """Restore the exact pre-migration Router files and old service state."""
    if not STATE.is_file() or STATE.is_symlink():
        raise ValueError("No cabinet Controller Router migration is available to roll back.")
    state = json.loads(STATE.read_text())
    subprocess.run(("systemctl", "disable", "--now", ROUTER_SERVICE), check=False)
    _restore(ROUTER_CONFIG, state.get("router_config"))
    _restore(FCEUMM_CONFIG, state.get("fceumm_config"), 0o644)
    if state.get("old_enabled"):
        _run("systemctl", "enable", OLD_SERVICE)
    if state.get("old_active"):
        _run("systemctl", "start", OLD_SERVICE)
    _run("systemctl", "restart", "virtualglove-receiver.service")
    STATE.unlink()
    print("PASS  Previous arcade merger and RetroArch settings restored.")


def apply(proposal_path: Path) -> None:
    """Apply a recently validated proposal, rolling back automatically on failure."""
    if os.geteuid() != 0:
        raise ValueError("Run cabinet migration as root.")
    if fceumm_running():
        raise ValueError("Close the running FCEUmm game before migration.")
    if STATE.exists():
        raise ValueError("A cabinet migration is already active; roll it back before retrying.")
    proposal = load_config(proposal_path)
    receipt = json.loads(RECEIPT.read_text()) if RECEIPT.is_file() else {}
    if (receipt.get("revision") != revision(proposal)
            or time.time() - receipt.get("checked_at", 0) > 3600):
        raise ValueError("Run a fresh cabinet preflight for this exact proposal first.")
    state = {"format": 1, "router_config": _saved_text(ROUTER_CONFIG),
             "fceumm_config": _saved_text(FCEUMM_CONFIG),
             "old_enabled": _service_state(OLD_SERVICE, "is-enabled"),
             "old_active": _service_state(OLD_SERVICE, "is-active")}
    atomic_write(STATE, json.dumps(state, indent=2) + "\n")
    try:
        atomic_write(ROUTER_CONFIG, json.dumps(proposal, indent=2) + "\n")
        _run("systemctl", "enable", "--now", ROUTER_SERVICE)
        if len(output_indexes(enabled_players(proposal))) != len(enabled_players(proposal)):
            raise RuntimeError("Controller Router outputs did not become ready.")
        _run("systemctl", "disable", "--now", OLD_SERVICE)
        _run("systemctl", "restart", "virtualglove-receiver.service")
    except Exception:
        rollback()
        raise
    print("PASS  Controller Router activated; the previous merger remains available for rollback.")


def main() -> int:
    """Run the explicit cabinet check, apply, or rollback action."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "apply", "rollback"))
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--watch-ms", type=int, default=5000)
    args = parser.parse_args()
    if args.action in ("check", "apply") and args.proposal is None:
        parser.error("check and apply require --proposal")
    if args.action == "check":
        check(args.proposal, max(1000, min(15000, args.watch_ms)))
    elif args.action == "apply":
        apply(args.proposal)
    else:
        rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
