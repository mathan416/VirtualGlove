# Project: Controller Router library
# Purpose: Route configured Linux controllers to Players 1-4.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Historical VirtualGlove configuration names remain compatible.

"""Versioned controller routing for RetroPie, Recalbox, and Batocera."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import select
import socket
import struct
import subprocess
import sys
import threading
import time
import secrets
import urllib.request
from pathlib import Path
from typing import Any

from .storage import atomic_write
from .systems import catalog
from .retroarch_udev import retroarch_udev_event_nodes, retroarch_index_for_js
from .merged_gamepad import (
    AXIS_CODES, BUTTON_NAMES, DIRECTION_NAMES, ANALOG_NAMES,
    CANONICAL_AXIS_INDEX, CANONICAL_BUTTON_INDEX, MERGED_RETROARCH_BINDINGS,
    controller_candidates, find_saved_controller,
    platform_hotkey_bindings, UInputMergedGamepad, merged_joypad_index,
    PhysicalMapper, translate_es_mapping, input_axis_ranges, virtual_state,
    EVIOCGRAB, EV_KEY, EV_ABS, VIRTUAL_TIMEOUT_SECONDS,
    _valid_input_code,
)

FORMAT = 2
SUPPORTED_PLATFORMS = ("retropie", "recalbox", "batocera")
MAX_SOURCES = 16
DEVICE_NAME = "VirtualGlove Merged Player {}"
DEVICE_PRODUCT_BASE = 0x5650
CONFIG_NAME = "controller-router.json"
DISCOVERY_INTERVAL_SECONDS = 1.0
VIRTUAL_DRAIN_LIMIT = 256
MAX_REQUEST = 262144
CONTROL_TEST_MS = 10_000


def detect_platform() -> str:
    """Detect the supported console platform without relying on its hostname."""
    if Path("/recalbox/recalbox.version").is_file():
        return "recalbox"
    if Path("/usr/share/batocera/batocera.version").is_file():
        return "batocera"
    if Path("/opt/retropie").is_dir():
        return "retropie"
    raise ValueError("Cannot detect RetroPie, Recalbox, or Batocera; use --platform.")


def _valid_mapping(mapping: object) -> bool:
    """Accept the bounded mapping schema already written by EmulationStation import."""
    if not isinstance(mapping, list) or not 1 <= len(mapping) <= 64:
        return False
    allowed = {"name", "type", "code", "value", "evdev_code"}
    for item in mapping:
        if not isinstance(item, dict) or not {"name", "type", "code", "value"} <= set(item):
            return False
        if set(item) - allowed:
            return False
        if (item["name"] not in BUTTON_NAMES and item["name"] not in DIRECTION_NAMES
                and item["name"] not in ANALOG_NAMES):
            return False
        if item["type"] not in ("button", "axis", "hat"):
            return False
        for key in ("code", "value"):
            if isinstance(item[key], bool) or not isinstance(item[key], int):
                return False
        if not _valid_input_code(item["type"], item["code"]):
            return False
        if not -0x8000 <= item["value"] <= 0x7FFF:
            return False
        if "evdev_code" in item and (isinstance(item["evdev_code"], bool)
                                      or not isinstance(item["evdev_code"], int)
                                      or not _valid_input_code(item["type"], item["evdev_code"])):
            return False
    return True


def _saved_source(candidate: dict[str, Any]) -> dict[str, Any]:
    """Strip transient event/js paths from an authoritative discovered source."""
    keys = ("id", "name", "guid", "vendor", "product", "version", "uniq", "phys", "mapping")
    result = {key: candidate.get(key, [] if key == "mapping" else "") for key in keys}
    for key in keys[:-1]:
        if not isinstance(result[key], str) or len(result[key]) > 512:
            raise ValueError("Controller identity is malformed.")
    if not result["id"] or not result["name"] or not _valid_mapping(result["mapping"]):
        raise ValueError("Controller inventory entry is incomplete.")
    return result


def mapping_revision(mapping: object) -> str:
    """Return a stable fingerprint for one validated EmulationStation mapping."""
    if not _valid_mapping(mapping):
        return ""
    return hashlib.sha256(json.dumps(mapping, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def session_mapping(saved: dict[str, Any], candidate: dict[str, Any]) -> list[dict]:
    """Combine refreshed frontend controls with saved physical-only hotkeys."""
    mapping = copy.deepcopy(candidate["mapping"])
    saved_hotkeys = [item for item in saved.get("mapping", [])
                     if item.get("name") == "hotkey"]
    if saved_hotkeys and not any(item.get("name") == "hotkey" for item in mapping):
        mapping.extend(saved_hotkeys)
    return mapping


def validate_config(data: object) -> dict[str, Any]:
    """Validate and normalize one complete router document."""
    if not isinstance(data, dict) or set(data) - {
            "format", "platform", "players", "virtualglove_player", "physical_scope", "physical_systems"}:
        raise ValueError("Invalid Controller Router configuration.")
    if data.get("format") != FORMAT:
        raise ValueError("Unsupported Controller Router configuration version.")
    if data.get("platform") not in SUPPORTED_PLATFORMS:
        raise ValueError("Choose RetroPie, Recalbox, or Batocera.")
    from .systems import policy
    physical_scope, physical_systems = policy(data)
    virtual_player = data.get("virtualglove_player")
    if isinstance(virtual_player, bool) or virtual_player not in (None, 1, 2, 3, 4):
        raise ValueError("VirtualGlove must be unassigned or assigned to one player.")
    players = data.get("players")
    if not isinstance(players, list) or len(players) > 4:
        raise ValueError("Controller Router supports Players 1 through 4.")
    seen_players: set[int] = set()
    seen_sources: set[str] = set()
    normalized = []
    for entry in players:
        if not isinstance(entry, dict) or set(entry) != {"player", "sources"}:
            raise ValueError("Invalid player assignment.")
        player, sources = entry["player"], entry["sources"]
        if isinstance(player, bool) or player not in (1, 2, 3, 4) or player in seen_players:
            raise ValueError("Each player slot may appear only once.")
        if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
            raise ValueError("Too many physical controller sources.")
        saved = []
        for source in sources:
            clean = _saved_source(source)
            if clean["id"] in seen_sources:
                raise ValueError("A physical controller cannot be assigned to multiple players.")
            seen_sources.add(clean["id"])
            saved.append(clean)
        seen_players.add(player)
        normalized.append({"player": player, "sources": saved})
    if len(seen_sources) > MAX_SOURCES:
        raise ValueError("Too many physical controller sources.")
    return {"format": FORMAT, "platform": data["platform"],
            "players": sorted(normalized, key=lambda item: item["player"]),
            "virtualglove_player": data.get("virtualglove_player"),
            "physical_scope": physical_scope,
            **({"physical_systems": physical_systems} if "physical_systems" in data or physical_scope == "systems" else {})}


def load_config(path: Path) -> dict[str, Any]:
    """Load a current router document."""
    return validate_config(json.loads(Path(path).read_text()))


def migrate_player1(old_path: Path, new_path: Path, platform: str) -> dict[str, Any] | None:
    """Migrate the released Recalbox/Batocera Player 1 record without altering it."""
    if Path(new_path).exists() or not Path(old_path).exists():
        return load_config(new_path) if Path(new_path).exists() else None
    from .merged_gamepad import load_controller
    old = load_controller(old_path)
    if platform not in ("recalbox", "batocera") or old.get("platform") != platform:
        raise ValueError("The existing merged controller belongs to a different platform.")
    config = validate_config({"format": FORMAT, "platform": platform,
                              "players": [{"player": 1, "sources": [old]}],
                              "virtualglove_player": 1, "physical_scope": "all"})
    atomic_write(new_path, json.dumps(config, indent=2) + "\n")
    return config


def enabled_players(config: dict[str, Any]) -> list[int]:
    """Return slots that need an output because they have a physical or glove source."""
    result = {entry["player"] for entry in config["players"] if entry["sources"]}
    if config.get("virtualglove_player"):
        result.add(config["virtualglove_player"])
    return sorted(result)


def inventory(es_inputs: Path, config: dict[str, Any] | None = None,
              *, sys_root: Path = Path("/sys/class/input"),
              dev_root: Path = Path("/dev/input")) -> list[dict[str, Any]]:
    """Return bounded public metadata for configured EmulationStation controllers."""
    connected = controller_candidates(es_inputs, sys_root, dev_root)
    saved = [(entry["player"], source) for entry in (config or {}).get("players", [])
             for source in entry["sources"]]
    resolved: dict[str, tuple[int, dict[str, Any]]] = {}
    for player, source in saved:
        match = find_saved_controller(source, connected)
        if match is not None:
            resolved[match["id"]] = (player, source)
    results = []
    seen_connected: set[str] = set()
    for item in connected:
        if item["id"] in seen_connected:
            continue
        seen_connected.add(item["id"])
        order = len(results) + 1
        assignment = resolved.get(item["id"])
        public_id = assignment[1]["id"] if assignment else item["id"]
        mapping_status = "current"
        if assignment and mapping_revision(item["mapping"]) != mapping_revision(assignment[1]["mapping"]):
            mapping_status = "refreshed"
        results.append({"id": public_id, "name": item["name"],
                        "identity_suffix": public_id[-6:], "connected": True,
                        "mapping_status": mapping_status,
                        "assigned_player": assignment[0] if assignment else None,
                        "suggested_player": order if order <= 4 else None})
    visible = {item["id"] for item in results}
    if config:
        for entry in config["players"]:
            for source in entry["sources"]:
                if source["id"] in visible:
                    continue
                results.append({"id": source["id"], "name": source["name"],
                                "identity_suffix": source["id"][-6:], "connected": False,
                                "mapping_status": "unavailable",
                                "assigned_player": entry["player"], "suggested_player": None})
    return results


def test_activity(es_inputs: Path, duration_ms: int = 500,
                  *, sys_root: Path = Path("/sys/class/input"),
                  dev_root: Path = Path("/dev/input")) -> dict[str, list[str]]:
    """Observe a short, non-grabbing controller window and return logical controls only."""
    duration_ms = max(0, min(CONTROL_TEST_MS, int(duration_ms)))
    event = struct.Struct("llHHi")
    opened: dict[int, tuple[str, list[dict[str, Any]]]] = {}
    try:
        for candidate in controller_candidates(es_inputs, sys_root, dev_root):
            joy_fd = None
            try:
                joy_fd = os.open(candidate["joystick"], os.O_RDONLY | os.O_NONBLOCK)
                mapping = translate_es_mapping(candidate["mapping"], joy_fd)
                fd = os.open(candidate["event"], os.O_RDONLY | os.O_NONBLOCK)
                opened[fd] = (candidate["id"], mapping)
            except (OSError, ValueError):
                continue
            finally:
                if joy_fd is not None: os.close(joy_fd)
        found: dict[str, set[str]] = {identity: set() for identity, _ in opened.values()}
        deadline = time.monotonic() + duration_ms / 1000.0
        while opened and time.monotonic() < deadline:
            ready, _, _ = select.select(
                list(opened), [], [], max(0.0, min(0.05, deadline - time.monotonic())))
            for fd in ready:
                try: payload = os.read(fd, event.size * 64)
                except OSError: continue
                identity, mapping = opened[fd]
                for offset in range(0, len(payload) - event.size + 1, event.size):
                    _sec, _usec, kind, code, value = event.unpack_from(payload, offset)
                    for item in mapping:
                        if item["code"] != code: continue
                        active = (kind == EV_KEY and item["type"] == "button" and value != 0)
                        if kind == EV_ABS and item["type"] in ("axis", "hat"):
                            active = (value < 0 if item["value"] < 0 else value > 0)
                        if active: found[identity].add(item["name"])
        return {identity: sorted(values) for identity, values in found.items() if values}
    finally:
        for fd in opened:
            os.close(fd)


class SourceState:
    """Hold one source independently so disconnects release only its controls."""
    def __init__(self) -> None:
        self.buttons: set[str] = set()
        self.axes = {name: 0 for name in AXIS_CODES}
        self.axis_changed = {name: 0.0 for name in AXIS_CODES}

    def release(self) -> None:
        """Release controls owned by only this source."""
        self.buttons.clear()
        for name in self.axes:
            self.axes[name] = 0
            self.axis_changed[name] = 0.0

    def set_axis(self, name: str, value: int, now: float | None = None) -> None:
        """Update one axis and its ownership timestamp."""
        value = int(value)
        if value != self.axes[name]:
            self.axes[name] = value
            self.axis_changed[name] = time.monotonic() if now is None else now


class PlayerState:
    """Combine any number of physical sources and one optional VirtualGlove."""
    def __init__(self, player: int) -> None:
        self.player = player
        self.physical: dict[str, SourceState] = {}
        self.virtual = SourceState()
        self.active = False

    def desired(self) -> tuple[set[str], dict[str, int]]:
        """Compute merged output with physical axis priority."""
        if not self.active:
            return set(), {name: 0 for name in AXIS_CODES}
        # Ordinary buttons are an OR of all sources. A physical hotkey is
        # deliberately special: only Player 1 may pass it to RetroArch, and
        # VirtualGlove's Select never creates that hotkey button.
        buttons = set().union(*(state.buttons for state in self.physical.values()),
                              self.virtual.buttons)
        if self.player != 1:
            buttons.discard("hotkey")
        physical_movement = any(value for state in self.physical.values()
                                for value in state.axes.values())
        axes = {}
        for axis in AXIS_CODES:
            # Event numbers are transient, so ownership is based on each
            # source's last actual axis change. A still-held older source
            # resumes automatically when the newer source returns to centre.
            owners = [state for state in self.physical.values() if state.axes[axis]]
            if owners:
                owner = max(owners, key=lambda state: state.axis_changed[axis])
                axes[axis] = owner.axes[axis]
            else:
                axes[axis] = 0 if physical_movement else self.virtual.axes[axis]
        return buttons, axes


class _MapperState:
    """Adapt one independent source to the proven single-source event mapper."""
    def __init__(self, source: SourceState) -> None:
        self.physical_buttons, self.physical_axes = source.buttons, source.axes


JOYSTICK_CORE_NAMES = {"fceumm_libretro.so", "nestopia_libretro.so"}
NATIVE_CORE_NAMES = {"nestopia_powerglove_libretro.so"}
PHYSICAL_NES_CORE_NAMES = JOYSTICK_CORE_NAMES | NATIVE_CORE_NAMES | {
    "rob_vision_fceumm_libretro.so", "rob_vision_nestopia_libretro.so",
    "robvision_fceumm_libretro.so", "robvision_nestopia_libretro.so",
}


def routes_physical_core(config: dict[str, Any], core: str | None, system: str | None = None) -> bool:
    from .systems import routes
    return routes(config, core, system, PHYSICAL_NES_CORE_NAMES)


def running_retroarch_session(proc_root: Path = Path("/proc")) -> tuple[str | None, str | None]:
    """Return the core and explicit system identity for the active frontend."""
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return None, None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [os.fsdecode(value) for value in raw if value]
        if not args or not Path(args[0]).name.casefold().startswith("retroarch"):
            continue
        from .systems import argument_system, system_id
        system = argument_system(args)
        try:
            for item in (entry / "environ").read_bytes().split(b"\0"):
                if item.startswith(b"CONTROLLER_ROUTER_SYSTEM="):
                    system = system_id(os.fsdecode(item.split(b"=", 1)[1]))
        except (OSError, ValueError):
            pass
        for value in args:
            if value.startswith("--libretro="):
                return Path(value.split("=", 1)[1]).name.casefold(), system
        for index, value in enumerate(args[:-1]):
            if value in ("-L", "--libretro"):
                return Path(args[index + 1]).name.casefold(), system
    return None, None


def running_retroarch_core(proc_root: Path = Path("/proc")) -> str | None:
    return running_retroarch_session(proc_root)[0]


def retroarch_running(proc_root: Path = Path("/proc")) -> bool:
    """Report whether any Libretro core is active."""
    return running_retroarch_core(proc_root) is not None


def joystick_core_running(proc_root: Path = Path("/proc")) -> bool:
    """Recognise NES cores that accept VirtualGlove as a RetroPad."""
    return running_retroarch_core(proc_root) in JOYSTICK_CORE_NAMES | NATIVE_CORE_NAMES


def virtual_joystick_core_running(proc_root: Path = Path("/proc")) -> bool:
    """Exclude native Super Glove Ball from duplicate RetroPad injection."""
    return running_retroarch_core(proc_root) in JOYSTICK_CORE_NAMES






class ControllerRouterDevice:
    """Own Player 1-4 outputs and dynamically reconnect their physical sources."""
    EVENT = struct.Struct("llHHi")

    def __init__(self, config_path: Path, retroarch_config: Path,
                 socket_path: Path | None = None, *, sinks: dict[int, Any] | None = None,
                 es_inputs: Path | None = None,
                 global_config: Path | None = None,
                 platform_config: Path | None = None,
                 proc_root: Path = Path("/proc"), sys_root: Path = Path("/sys/class/input"),
                 udev_root: Path = Path("/run/udev/data"), dev_root: Path = Path("/dev/input")) -> None:
        self.config_path, self.config = Path(config_path), load_config(config_path)
        self.retroarch_config, self.proc_root = Path(retroarch_config), proc_root
        self.global_config = Path(global_config) if global_config else None
        self.platform_config = Path(platform_config) if platform_config else None
        self.es_inputs = Path(es_inputs) if es_inputs else _paths(self.config["platform"])[1]
        self.sys_root, self.udev_root, self.dev_root = sys_root, udev_root, dev_root
        self.players = {player: PlayerState(player) for player in enabled_players(self.config)}
        if sinks is None and running_retroarch_core(self.proc_root) is not None:
            raise RuntimeError("Router restarted during play; exit and relaunch the game to restore merged controllers")
        self.owner_lock = None
        self.sinks = sinks if sinks is not None else {}
        if sinks is None and self.sys_root == Path('/sys/class/input'):
            # Both products can start together. Acquire ownership before
            # creating any pad or replacing the shared socket.
            self.owner_lock = acquire_output_owner(Path('/run/virtualglove/controller-router-owner.lock'))
        try:
            if sinks is None:
                for player in self.players:
                    self.sinks[player] = UInputMergedGamepad(
                        name=output_name(player), product=DEVICE_PRODUCT_BASE + player)
        except Exception:
            for sink in self.sinks.values():
                sink.close()
            if self.owner_lock is not None:
                os.close(self.owner_lock)
            raise
        self.descriptors: dict[int, dict[str, Any]] = {}
        self.socket_path, self.socket = socket_path, None
        self.virtual_updated_at = 0.0
        self.virtual_allowed = False
        # A newly launched core must begin from a fresh neutral glove state.
        # Otherwise the last observation received while EmulationStation was
        # active can become the game's first controller input.
        self.virtual_armed = False
        self.session_mapping_revisions: dict[str, str] = {}
        self.config_revision = revision(self.config)
        self.config_checked_at = 0.0
        self.discovery_checked_at = 0.0
        self.installed_indexes: dict[int, int] = {}
        self.installed_hotkeys: dict[str, str] = {}
        self.stop = threading.Event()
        self.lock = threading.Lock()
        try:
            self._install_indexes()
            if socket_path:
                socket_path.parent.mkdir(parents=True, exist_ok=True)
                if socket_path.is_symlink():
                    raise ValueError("refusing symbolic Controller Router socket")
                try:
                    socket_path.unlink()
                except FileNotFoundError:
                    pass
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                self.socket.bind(str(socket_path)); os.chmod(socket_path, 0o660)
                self.socket.setblocking(False)
        except Exception:
            if self.socket is not None:
                self.socket.close()
            for sink in self.sinks.values():
                sink.close()
            if self.owner_lock is not None:
                os.close(self.owner_lock)
            raise
        self.thread = threading.Thread(target=self._run, name="virtualglove-controller-router", daemon=True)
        self.thread.start()

    def _install_indexes(self) -> None:
        """Wait for output readiness without writing any RetroArch configuration."""
        for _attempt in range(100):
            indexes = output_indexes(list(self.players), self.sys_root, self.udev_root,
                                     self.config["platform"])
            if len(indexes) == len(self.players):
                self.installed_indexes = indexes
                # Public runtime manifest contains output slots only, never
                # pairing credentials or physical source configuration.
                if self.sys_root == Path("/sys/class/input"):
                    atomic_write(Path("/run/virtualglove/controller-router-launch.json"),
                                 json.dumps({"schema": 1, "platform": self.config["platform"],
                                             "outputs": list(self.players),
                                             "physical_scope": self.config.get("physical_scope", "all"),
                                             "physical_systems": self.config.get("physical_systems", [])}) + "\n", 0o644)
                return
            time.sleep(0.05)
        raise RuntimeError("Controller Router outputs did not appear; relaunch after repairing the service")

    def _set_active(self, active: bool,
                    candidates: list[dict[str, Any]] | None = None,
                    virtual_allowed: bool = True) -> None:
        """Grab or release physical sources across a supported-core transition."""
        if active:
            # Freeze the mapping revision for this game. A frontend remap made
            # mid-session takes effect next launch, never halfway through play.
            available = candidates if candidates is not None else (
                self._current_candidates() if hasattr(self, "es_inputs") else [])
            self.session_mapping_revisions = {}
            for _player, saved in self._saved_sources():
                candidate = find_saved_controller(saved, available)
                mapping = session_mapping(saved, candidate) if candidate else saved["mapping"]
                self.session_mapping_revisions[saved["id"]] = mapping_revision(mapping)
        else:
            self.session_mapping_revisions.clear()
        for fd, record in list(self.descriptors.items()):
            if record["grabbed"] != active:
                try:
                    fcntl.ioctl(record["fd"], EVIOCGRAB, int(active))
                    record["grabbed"] = active
                except OSError:
                    self._drop(fd)
        for state in self.players.values():
            state.active = active
            state.virtual.release()
        # No pose seen in EmulationStation or a previous game may become the
        # first action in a newly launched game; require a fresh neutral pose.
        self.virtual_allowed = bool(active and virtual_allowed)
        self.virtual_updated_at = 0.0
        self.virtual_armed = False
        self._publish()

    def _reload_config(self, updated: dict[str, Any]) -> None:
        """Refresh idle assignments without destroying existing output devices."""
        previous, previous_revision = self.config, self.config_revision
        previous_players = self.players
        created = []
        for fd in list(self.descriptors):
            self._drop(fd)
        # Keep even a newly unassigned output neutral until service shutdown.
        # Removing pads beneath EmulationStation can crash older SDL frontends.
        for sink in self.sinks.values():
            sink.write(set(), {name: 0 for name in AXIS_CODES})
        try:
            for player in enabled_players(updated):
                if player not in self.sinks:
                    self.sinks[player] = UInputMergedGamepad(
                        name=output_name(player), product=DEVICE_PRODUCT_BASE + player)
                    created.append(player)
            self.config = updated
            self.players = {player: PlayerState(player) for player in enabled_players(updated)}
            self.config_revision = revision(updated)
            self._install_indexes()
        except Exception:
            for player in created:
                self.sinks.pop(player).close()
            self.config, self.config_revision = previous, previous_revision
            self.players = previous_players
            self._install_indexes()
            raise

    def _publish(self) -> None:
        """Write all merged player states to their independent outputs."""
        for player, state in self.players.items():
            self.sinks[player].write(*state.desired())

    def _saved_sources(self) -> list[tuple[int, dict[str, Any]]]:
        """Flatten configured physical sources with their player slot."""
        return [(entry["player"], source)
                for entry in getattr(self, "config", {}).get("players", [])
                for source in entry["sources"]]

    def _current_candidates(self) -> list[dict[str, Any]]:
        """Read currently connected devices with their live frontend mappings."""
        return controller_candidates(self.es_inputs, self.sys_root, self.dev_root)

    def _refresh_idle_mappings(self, candidates: list[dict[str, Any]]) -> None:
        """Drop idle descriptors whose validated EmulationStation mapping changed."""
        saved_by_id = {source["id"]: source for _player, source in self._saved_sources()}
        for fd, record in list(self.descriptors.items()):
            saved = saved_by_id.get(record["source_id"])
            candidate = find_saved_controller(saved, candidates) if saved else None
            current = mapping_revision(session_mapping(saved, candidate)) if candidate else ""
            if not current or current != record.get("mapping_revision"):
                self._drop(fd)

    def _discover(self, candidates: list[dict[str, Any]] | None = None) -> None:
        """Reconnect saved identities using current validated frontend mappings."""
        candidates = candidates if candidates is not None else self._current_candidates()
        connected_ids = {record["source_id"] for record in self.descriptors.values()}
        for player, saved in self._saved_sources():
            if saved["id"] in connected_ids:
                continue
            candidate = find_saved_controller(saved, candidates)
            if candidate is None:
                continue
            live_mapping = session_mapping(saved, candidate)
            live_revision = mapping_revision(live_mapping)
            expected_revision = self.session_mapping_revisions.get(saved["id"])
            if self.players[player].active and live_revision != expected_revision:
                # EmulationStation changes apply only after the running game
                # exits, so a reconnect cannot silently change button meaning.
                continue
            joy_fd = event_fd = None
            try:
                # js exposes the frontend's logical button numbering; evdev
                # supplies live events and EVIOCGRAB. Both refer to the same
                # saved physical identity, never to persisted jsN/eventN paths.
                joy_fd = os.open(candidate["joystick"], os.O_RDONLY | os.O_NONBLOCK)
                mapping = translate_es_mapping(live_mapping, joy_fd)
                event_fd = os.open(candidate["event"], os.O_RDONLY | os.O_NONBLOCK)
                source = self.players[player].physical.setdefault(saved["id"], SourceState())
                mapper = PhysicalMapper(mapping, _MapperState(source), input_axis_ranges(event_fd, mapping))
                active = self.players[player].active
                if active:
                    fcntl.ioctl(event_fd, EVIOCGRAB, 1)
                self.descriptors[event_fd] = {"fd": event_fd, "source_id": saved["id"],
                                              "player": player, "source": source,
                                              "mapper": mapper, "grabbed": active,
                                              "mapping_revision": live_revision}
                event_fd = None
            except (OSError, ValueError):
                pass
            finally:
                if joy_fd is not None: os.close(joy_fd)
                if event_fd is not None: os.close(event_fd)

    def _drop(self, fd: int) -> None:
        """Release and close one disconnected physical source."""
        record = self.descriptors.pop(fd)
        try:
            if record["grabbed"]: fcntl.ioctl(fd, EVIOCGRAB, 0)
        except OSError:
            pass
        os.close(fd); record["source"].release(); self._publish()

    def _virtual(self, incoming: dict[str, Any]) -> None:
        """Map one validated VirtualGlove state to its configured player."""
        player = self.config.get("virtualglove_player")
        if not player or player not in self.players:
            return
        player_state = self.players[player]
        state = player_state.virtual
        if not player_state.active or not self.virtual_allowed:
            # Observations from Setup or EmulationStation must never be held
            # and replayed when the next game starts.
            state.release()
            self.virtual_updated_at = 0.0
            return
        buttons = incoming.get("buttons", {})
        dpad = incoming.get("dpad", {})
        neutral = not any(bool(buttons.get(name)) for name in (
            "a", "b", "start", "select", "glove_zap"
        )) and not any(bool(dpad.get(name)) for name in (
            "left", "right", "up", "down"
        ))
        if not self.virtual_armed:
            state.release()
            if neutral:
                self.virtual_armed = True
                self.virtual_updated_at = time.monotonic()
            self._publish()
            return

        state.release()
        for name in ("a", "b", "start", "select"):
            if buttons.get(name): state.buttons.add(name)
        if buttons.get("glove_zap"): state.buttons.add("r2")
        state.set_axis("hat_x", int(bool(dpad.get("right"))) - int(bool(dpad.get("left"))))
        state.set_axis("hat_y", int(bool(dpad.get("down"))) - int(bool(dpad.get("up"))))
        # FCEUmm and stock Nestopia consume the recognised NES D-pad. Camera
        # position axes belong to the separate native Super Glove Ball path;
        # forwarding them here can hold an ordinary game off-centre at launch.
        self.virtual_updated_at = time.monotonic(); self._publish()

    def _drain_virtual(self) -> None:
        """Discard queued history and apply only the newest valid glove state."""
        queued = []
        for _packet in range(VIRTUAL_DRAIN_LIMIT):
            try:
                queued.append(self.socket.recv(8193))
            except BlockingIOError:
                break
            except OSError:
                return
        # Decode from newest to oldest so malformed traffic cannot hide the
        # newest valid state, while avoiding JSON work for discarded history.
        for payload in reversed(queued):
            try:
                incoming = virtual_state(json.loads(payload)) if len(payload) <= 8192 else None
            except (ValueError, UnicodeError, json.JSONDecodeError):
                continue
            if incoming is not None:
                self._virtual(incoming)
                return

    def _run(self) -> None:
        """Monitor routed games, configuration, hot-plug, and source events."""
        active = virtual_allowed = False
        while not self.stop.is_set():
            with self.lock:
                core, system = running_retroarch_session(self.proc_root)
                now_active = routes_physical_core(self.config, core, system)
                now_virtual_allowed = now_active and core in JOYSTICK_CORE_NAMES
                if (now_active, now_virtual_allowed) != (active, virtual_allowed):
                    # Native Super Glove Ball still needs the physical merged
                    # pad for menu/hotkey use, but its hand position arrives
                    # through native state, not the RetroPad glove feed.
                    candidates = None
                    if now_active:
                        candidates = self._current_candidates()
                        self._refresh_idle_mappings(candidates)
                        self._discover(candidates)
                    if now_active and output_indexes(list(self.players), self.sys_root,
                                                     self.udev_root,
                                                     self.config["platform"]) != self.installed_indexes:
                        self._install_indexes()
                    active, virtual_allowed = now_active, now_virtual_allowed
                    self._set_active(active, candidates, virtual_allowed)
                if self.virtual_updated_at and time.monotonic() - self.virtual_updated_at >= VIRTUAL_TIMEOUT_SECONDS:
                    player = self.config.get("virtualglove_player")
                    if player in self.players: self.players[player].virtual.release()
                    self.virtual_updated_at = 0.0; self._publish()
                if not active and time.monotonic() - self.config_checked_at >= 1.0:
                    try:
                        updated = load_config(self.config_path)
                        if revision(updated) != self.config_revision:
                            self._reload_config(updated)
                        elif output_indexes(list(self.players), self.sys_root,
                                            self.udev_root,
                                            self.config["platform"]) != self.installed_indexes:
                            self._install_indexes()
                        elif self.config["platform"] == "recalbox":
                            global_path = self.global_config or self.retroarch_config.with_name(
                                "retroarchcustom.cfg")
                            global_text = unmanaged_retroarch_config(
                                global_path.read_text() if global_path.exists() else "")
                            if player_one_hotkeys(self.config, global_text) != self.installed_hotkeys:
                                self._install_indexes()
                    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                        pass
                    self.config_checked_at = time.monotonic()
                if time.monotonic() - self.discovery_checked_at >= DISCOVERY_INTERVAL_SECONDS:
                    candidates = self._current_candidates()
                    if not active:
                        self._refresh_idle_mappings(candidates)
                    self._discover(candidates)
                    self.discovery_checked_at = time.monotonic()
            sources = list(self.descriptors)
            if self.socket is not None: sources.append(self.socket)
            if not sources:
                self.stop.wait(0.2); continue
            try:
                ready, _, _ = select.select(sources, [], [], 0.1)
            except (OSError, ValueError):
                continue
            with self.lock:
                for fd in [value for value in ready if isinstance(value, int)]:
                    try:
                        payload = os.read(fd, self.EVENT.size * 64)
                        if not payload: raise OSError("controller disconnected")
                        mapper = self.descriptors[fd]["mapper"]
                        source = self.descriptors[fd]["source"]
                        for offset in range(0, len(payload) - self.EVENT.size + 1, self.EVENT.size):
                            _sec, _usec, kind, code, value = self.EVENT.unpack_from(payload, offset)
                            if kind in (EV_KEY, EV_ABS):
                                before = dict(source.axes)
                                mapper.event(kind, code, value)
                                for axis in AXIS_CODES:
                                    if source.axes[axis] != before[axis]:
                                        source.axis_changed[axis] = time.monotonic()
                        self._publish()
                    except OSError:
                        self._drop(fd)
                # Physical sources are deliberately serviced first. A busy
                # camera stream must never delay an attached controller.
                if self.socket is not None and self.socket in ready:
                    self._drain_virtual()

    def close(self) -> None:
        """Neutralize and close every router-owned resource."""
        self.stop.set(); self.thread.join(timeout=2)
        for fd in list(self.descriptors): self._drop(fd)
        if self.socket is not None:
            self.socket.close()
            try: self.socket_path.unlink()
            except FileNotFoundError: pass
        for sink in self.sinks.values(): sink.close()
        if self.owner_lock is not None:
            os.close(self.owner_lock)
            self.owner_lock = None


def acquire_output_owner(path: Path) -> int:
    """Hold a process-lifetime lock so concurrent products cannot duplicate pads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError('Controller Router already owns the merged outputs; use the running shared service')
    except Exception:
        os.close(fd)
        raise
    try:
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode('ascii'))
    except Exception:
        os.close(fd)
        raise
    return fd


def output_name(player: int) -> str:
    """Return the stable uinput name for a bounded player slot."""
    if player not in (1, 2, 3, 4):
        raise ValueError("player must be between 1 and 4")
    return DEVICE_NAME.format(player)


def output_indexes(players: list[int], sys_root: Path = Path("/sys/class/input"),
                   udev_root: Path = Path("/run/udev/data"),
                   platform: str = "recalbox") -> dict[int, int]:
    """Resolve current platform-specific RetroArch indexes without persisting them."""
    found = {}
    retro_events = None
    if platform == "retropie":
        retro_events = retroarch_udev_event_nodes()
    for player in players:
        name = output_name(player)
        if platform == "retropie":
            joystick = next((int(item.name[2:]) for item in sorted(
                sys_root.glob("js*"), key=lambda path: int(path.name[2:]))
                if (item / "device/name").is_file()
                and (item / "device/name").read_text(errors="replace").strip() == name), None)
            if joystick is None:
                index = None
            else:
                try:
                    index = retroarch_index_for_js(joystick, sys_root, retro_events)
                except RuntimeError:
                    # uinput publishes jsN before udev marks the matching
                    # event node as a joystick. _install_indexes retries.
                    index = None
        else:
            index = merged_joypad_index(sys_root, udev_root, name)
        if index is not None:
            found[player] = index
    return found


def _player_bindings(player: int) -> dict[str, str]:
    """Translate canonical Player 1 binding keys to one target slot."""
    result = {}
    for key, value in MERGED_RETROARCH_BINDINGS.items():
        if key == "input_enable_hotkey_btn":
            if player == 1:
                result[key] = value
        else:
            result[key.replace("player1", "player%d" % player)] = value
    return result


def unmanaged_retroarch_config(text: str) -> str:
    """Exclude Router's own output when reading Recalbox's physical bindings."""
    markers = {
        "# VirtualGlove Controller Router": "# End VirtualGlove Controller Router",
        "# VirtualGlove merged Player 1": "# End VirtualGlove merged Player 1",
    }
    output, end_marker = [], None
    for line in text.splitlines():
        if end_marker is not None:
            if line.strip() == end_marker:
                end_marker = None
            continue
        end_marker = markers.get(line.strip())
        if end_marker is None and line.strip() != "# VirtualGlove Player 1 keyboard merge":
            output.append(line)
    return "\n".join(output)


def player_one_hotkeys(config: dict[str, Any], global_config: str) -> dict[str, str]:
    """Resolve the effective Player 1 hotkeys from the unmodified source."""
    player_one = next((entry for entry in config["players"] if entry["player"] == 1), None)
    if not player_one or not player_one["sources"]:
        return {}
    return platform_hotkey_bindings(
        {**player_one["sources"][0], "platform": config["platform"]}, global_config)








def revision(config: dict[str, Any]) -> str:
    """Hash normalized configuration independently of file formatting."""
    return hashlib.sha256((json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


class RouterStore:
    """Revision-checked configuration store with one-command rollback."""
    def __init__(self, path: Path, platform: str, es_inputs: Path,
                 retroarch_config: Path | None = None, activity_check=None,
                 activate=None) -> None:
        self.path, self.backup = Path(path), Path(str(path) + ".previous")
        self.platform, self.es_inputs = platform, Path(es_inputs)
        self.retroarch_config = Path(retroarch_config) if retroarch_config else None
        self.activity_check = activity_check or self._managed_game_running
        self.activate = activate
        self.lock = threading.Lock()

    def _managed_game_running(self) -> bool:
        """A scope edit must not activate routing halfway through any game."""
        return retroarch_running()

    def _default(self) -> dict[str, Any]:
        """Return an inactive configuration for an unconfigured platform."""
        return {"format": FORMAT, "platform": self.platform, "players": [],
                "virtualglove_player": None, "physical_scope": "nes"}

    def read(self) -> dict[str, Any]:
        """Return configuration, revision, rollback state, and inventory."""
        config = load_config(self.path) if self.path.exists() else self._default()
        return {"config": config, "revision": revision(config),
                "has_backup": self.backup.exists(),
                "inventory": inventory(self.es_inputs, config),
                "systems": catalog(self.platform, config)}

    def _materialize(self, proposed: object) -> dict[str, Any]:
        """Replace public source IDs with authoritative saved mappings."""
        if not isinstance(proposed, dict):
            raise ValueError("Controller Router configuration is missing.")
        candidates = {item["id"]: item for item in controller_candidates(self.es_inputs)}
        if self.path.exists():
            connected = list(candidates.values())
            for entry in load_config(self.path)["players"]:
                for source in entry["sources"]:
                    # A currently discovered exact-GUID record is authoritative.
                    # Retain the saved record only when the source is genuinely
                    # unavailable; never replace a refreshed mapping merely
                    # because its stable physical identity is unchanged.
                    if source["id"] in candidates:
                        # EmulationStation does not represent a cabinet's
                        # dedicated hotkey when it is intentionally outside
                        # the frontend controls. Preserve that one proven,
                        # physical-only mapping across assignment saves.
                        saved_hotkeys = [item for item in source["mapping"]
                                         if item.get("name") == "hotkey"]
                        discovered = candidates[source["id"]]
                        if (saved_hotkeys and not any(item.get("name") == "hotkey"
                                                     for item in discovered["mapping"])):
                            discovered = copy.deepcopy(discovered)
                            discovered["mapping"].extend(saved_hotkeys)
                            candidates[source["id"]] = discovered
                    else:
                        candidates[source["id"]] = find_saved_controller(source, connected) or source
        proposed_players = proposed.get("players", [])
        if not isinstance(proposed_players, list) or len(proposed_players) > 4:
            raise ValueError("Controller Router supports Players 1 through 4.")
        players = []
        for entry in proposed_players:
            if not isinstance(entry, dict) or set(entry) != {"player", "sources"}:
                raise ValueError("Invalid player assignment.")
            ids = entry["sources"]
            if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
                raise ValueError("Invalid physical controller assignment.")
            try:
                sources = [_saved_source(candidates[value]) for value in ids]
            except KeyError as exc:
                raise ValueError("A selected controller is no longer available. Refresh and try again.") from exc
            players.append({"player": entry.get("player"), "sources": sources})
        current = load_config(self.path) if self.path.exists() else self._default()
        return validate_config({"format": FORMAT, "platform": self.platform, "players": players,
                                "virtualglove_player": proposed.get("virtualglove_player"),
                                "physical_scope": proposed.get("physical_scope", current["physical_scope"]),
                                **({"physical_systems": proposed.get("physical_systems", current.get("physical_systems", []))}
                                   if "physical_systems" in proposed or "physical_systems" in current
                                   or proposed.get("physical_scope") == "systems" else {})})

    def operate(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Perform one bounded revision-checked router operation."""
        with self.lock:
            current = self.read()
            if operation in ("read", "inventory"):
                return current
            if operation == "check":
                config = current["config"]
                connected = {item["id"] for item in current["inventory"]
                             if item.get("connected") and item.get("assigned_player") is not None}
                missing = [source["id"] for entry in config["players"] for source in entry["sources"]
                           if source["id"] not in connected]
                activity = test_activity(self.es_inputs, payload.get("watch_ms", 0))
                return {**current, "enabled_players": enabled_players(config),
                        "missing_sources": missing, "activity": activity,
                        "safe": not missing}
            if operation not in ("save", "rollback"):
                raise ValueError("Unsupported Controller Router operation.")
            if self.activity_check():
                raise ValueError("Close the running RetroArch game before changing controller assignments.")
            if payload.get("revision") != current["revision"]:
                raise ValueError("Controller assignments changed elsewhere. Reload before saving.")
            if operation == "rollback":
                if not self.backup.exists():
                    raise ValueError("No previous Controller Router configuration is available.")
                next_config = load_config(self.backup)
            else:
                next_config = self._materialize(payload.get("config"))
            had_current = self.path.exists()
            previous_text = self.path.read_text() if had_current else None
            if previous_text is not None:
                atomic_write(self.backup, previous_text)
            atomic_write(self.path, json.dumps(next_config, indent=2) + "\n")
            if self.activate is not None:
                try:
                    self.activate()
                except (OSError, RuntimeError):
                    if previous_text is not None:
                        atomic_write(self.path, previous_text)
                    else:
                        if self.path.exists():
                            self.path.unlink()
                    raise ValueError("Assignments were not activated; the previous configuration was restored.")
            return self.read()


def _paths(platform: str) -> tuple[Path, Path, Path, Path, Path | None]:
    """Return fixed configuration paths for one supported console."""
    if platform == "recalbox":
        root = Path("/recalbox/share/system/virtualglove")
        retroarch = Path("/recalbox/share/system/configs/retroarch")
        return (root / "data/controller-router.json",
                Path("/recalbox/share/system/.emulationstation/es_input.cfg"),
                retroarch / "config/FCEUmm/FCEUmm.cfg",
                retroarch / "retroarchcustom.cfg", None)
    if platform == "batocera":
        root = Path("/userdata/system/virtualglove")
        retroarch = Path("/userdata/system/configs/retroarch")
        return (root / "data/controller-router.json",
                Path("/userdata/system/configs/emulationstation/es_input.cfg"),
                retroarch / "config/FCEUmm/FCEUmm.cfg",
                retroarch / "retroarchcustom.cfg",
                Path("/userdata/system/batocera.conf"))
    return (Path("/etc/virtualglove/controller-router.json"),
            Path("/opt/retropie/configs/all/emulationstation/es_input.cfg"),
            Path("/opt/retropie/configs/all/retroarch/config/FCEUmm/FCEUmm.cfg"),
            Path("/opt/retropie/configs/nes/retroarchcustom.cfg"), None)


def _assignment_label(player: int | None) -> str:
    """Return the compact label used by the terminal assignment table."""
    return "Player %d" % player if player else "Unassigned"


def _wizard_screen(state: dict[str, Any], assignments: dict[str, int | None],
                   virtual_player: int | None) -> str:
    """Render one dependency-free Controller Router terminal screen."""
    width = 78
    border = "+" + "-" * width + "+"

    def line(value: str = "") -> str:
        """Fit one row within the fixed-width terminal frame."""
        return "| " + value[:width - 2].ljust(width - 2) + " |"

    rows = []
    for index, source in enumerate(state["inventory"], 1):
        name = source["name"][:34]
        identity = source.get("identity_suffix", source["id"][-6:])
        connected = "Connected" if source.get("connected") else "Unavailable"
        rows.append(line("%2d   %-34s  %-6s  %-10s  %-11s" % (
            index, name, identity, _assignment_label(assignments.get(source["id"])), connected)))
    if not rows:
        rows.append(line("No configured EmulationStation controllers found."))
    lines = [
        "+" + " VirtualGlove Controller Router ".center(width, "-") + "+",
        line("Assign configured controllers to merged RetroArch players."),
        border,
        line("No.  Controller                          ID      Assignment  Status"),
        border,
        *rows,
        border,
        line("VirtualGlove: %s" % _assignment_label(virtual_player)),
        line("[1-%d] Assign controller   [V] VirtualGlove   [T] Test controls" %
             max(1, len(rows))),
        line("[S] Save and verify       [R] Roll back      [Q] Quit"),
        border,
    ]
    return "\n".join(lines)


def _choose_player(prompt: str, input_fn) -> int | None:
    """Read one bounded player assignment, using zero for Unassigned."""
    value = input_fn(prompt + " [0=Unassigned, 1-4=Player]: ").strip()
    if value not in ("0", "1", "2", "3", "4"):
        raise ValueError("Choose 0, 1, 2, 3, or 4.")
    return int(value) or None


def _wait_for_outputs(config: dict[str, Any], attempts: int = 50) -> bool:
    """Wait briefly for the Router service to publish every enabled output."""
    players = enabled_players(config)
    for _attempt in range(attempts):
        if len(output_indexes(players, platform=config["platform"])) == len(players):
            return True
        time.sleep(0.1)
    return False


def run_setup_wizard(store: RouterStore, input_fn=input, output_fn=print,
                     verify_fn=None) -> int:
    """Interactively review, test, save, or roll back local assignments."""
    state = store.read()
    assignments = {
        source["id"]: source.get("assigned_player") or source.get("suggested_player")
        for source in state["inventory"]
    }
    virtual_player = state["config"].get("virtualglove_player")
    while True:
        output_fn(_wizard_screen(state, assignments, virtual_player))
        choice = input_fn("Choice: ").strip().casefold()
        if choice == "q":
            output_fn("No Controller Router changes were saved.")
            return 0
        if choice == "v":
            try:
                virtual_player = _choose_player("VirtualGlove", input_fn)
            except ValueError as exc:
                output_fn("ACTION  " + str(exc))
            continue
        if choice == "t":
            output_fn("Press buttons or directions for the next 10 seconds...")
            result = store.operate("check", {"watch_ms": CONTROL_TEST_MS})
            if result["activity"]:
                names = {item["id"]: item["name"] for item in result["inventory"]}
                for identity, controls in result["activity"].items():
                    output_fn("PASS  %s: %s" % (names.get(identity, identity[-6:]),
                                                ", ".join(controls)))
            else:
                output_fn("ACTION  No control was pressed during the test.")
            if result["missing_sources"]:
                by_id = {item["id"]: item for item in result["inventory"]}
                for identity in result["missing_sources"]:
                    source = by_id.get(identity, {})
                    output_fn("ACTION  %s · %s%s is unavailable." % (
                        source.get("name", "Configured controller"),
                        source.get("identity_suffix", identity[-6:]),
                        " · Player %s" % source["assigned_player"]
                        if source.get("assigned_player") else ""))
            continue
        if choice == "r":
            if not state["has_backup"]:
                output_fn("ACTION  No previous assignment is available.")
                continue
            if input_fn("Restore the previous assignments? [y/N]: ").strip().casefold() != "y":
                continue
            state = store.operate("rollback", {"revision": state["revision"]})
            output_fn("PASS  Previous Controller Router assignments restored.")
            return 0
        if choice == "s":
            players = []
            for player in range(1, 5):
                sources = [identity for identity, assigned in assignments.items()
                           if assigned == player]
                if sources:
                    players.append({"player": player, "sources": sources})
            output_fn("Review: %s; VirtualGlove: %s." % (
                ", ".join("P%d=%d controller(s)" % (entry["player"], len(entry["sources"]))
                          for entry in players) or "no physical assignments",
                _assignment_label(virtual_player)))
            if input_fn("Save these assignments? [y/N]: ").strip().casefold() != "y":
                continue
            state = store.operate("save", {"revision": state["revision"],
                "config": {"players": players, "virtualglove_player": virtual_player}})
            verified = (verify_fn or _wait_for_outputs)(state["config"])
            if not verified:
                output_fn("ACTION  Assignments were saved, but the merged outputs could not be verified.")
                output_fn("Run the screen again to check or restore the previous assignments.")
                return 1
            output_fn("PASS  Controller Router assignments saved and outputs verified.")
            return 0
        if choice.isdigit() and 1 <= int(choice) <= len(state["inventory"]):
            source = state["inventory"][int(choice) - 1]
            try:
                assignments[source["id"]] = _choose_player(source["name"], input_fn)
            except ValueError as exc:
                output_fn("ACTION  " + str(exc))
            continue
        output_fn("ACTION  Choose a listed controller, V, T, S, R, or Q.")


def main() -> int:
    """Run the console-local Controller Router command line."""
    parser = argparse.ArgumentParser(prog="virtualglove-controller-router",
                                     description="Configure VirtualGlove Player 1-4 routing")
    parser.add_argument("command", choices=("setup", "list", "show", "configure", "check",
                                             "apply", "rollback", "serve", "prepare-launch"))
    parser.add_argument("--platform", choices=SUPPORTED_PLATFORMS,
                        help="Console platform; detected automatically when omitted")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--document", type=Path, help="JSON assignment document for configure")
    parser.add_argument("--socket", type=Path)
    parser.add_argument("--retroarch", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    platform = args.platform or detect_platform()
    default_config, es_inputs, retroarch, global_config, platform_config = _paths(platform)

    def activate_retropie() -> None:
        """Start RetroPie's opt-in Router after its first local wizard save."""
        if platform != "retropie":
            return
        subprocess.run(("systemctl", "enable", "--now",
                        "virtualglove-controller-router.service"), check=True)
        if subprocess.run(("systemctl", "cat", "virtualglove-receiver.service"),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(("systemctl", "restart", "virtualglove-receiver.service"), check=True)

    store = RouterStore(args.config or default_config, platform, es_inputs, retroarch,
                        activate=activate_retropie if platform == "retropie" else None)
    if args.command == "prepare-launch":
        if args.retroarch is None or args.output is None:
            parser.error("prepare-launch requires --retroarch and --output")
        from .launch import prepare
        try:
            print(json.dumps(prepare(load_config(args.config or default_config), args.retroarch, args.output)))
        except (OSError, ValueError, RuntimeError) as exc:
            print('Controller Router launch blocked: %s' % exc, file=sys.stderr)
            return 1
        return 0
    if args.command == "setup":
        return run_setup_wizard(store)
    if args.command == "serve":
        if args.socket is None:
            parser.error("serve requires --socket")
        try:
            device = ControllerRouterDevice(args.config or default_config, retroarch, args.socket,
                                            es_inputs=es_inputs, global_config=global_config,
                                            platform_config=platform_config)
        except (OSError, ValueError, RuntimeError) as exc:
            print('Controller Router: %s' % exc, file=sys.stderr)
            return 1
        try:
            while True: time.sleep(3600)
        except KeyboardInterrupt:
            return 0
        finally:
            device.close()
    elif args.command == "list":
        print(json.dumps(store.read()["inventory"], indent=2))
    elif args.command in ("show", "check"):
        print(json.dumps(store.operate("check" if args.command == "check" else "read", {}), indent=2))
    elif args.command == "configure":
        if args.document is None:
            parser.error("configure requires --document")
        current = store.read()
        payload = {"revision": current["revision"], "config": json.loads(args.document.read_text())}
        print(json.dumps(store.operate("save", payload), indent=2))
    elif args.command == "rollback":
        current = store.read()
        print(json.dumps(store.operate("rollback", {"revision": current["revision"]}), indent=2))
    else:
        # Compatibility command: readiness only. Routing belongs to prepare-launch.
        config = store.read()["config"]
        from .launch import resolve
        players = enabled_players(config)
        if len(resolve(players)) != len(players):
            raise RuntimeError("Controller Router outputs unavailable; check the service and relaunch")
        print("Controller Router ready; session routing is resolved at launch.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
