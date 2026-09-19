# Project: VirtualGlove
# File: src/virtualglove/controller_router.py
# Purpose: Route configured physical controllers and one VirtualGlove to Players 1-4.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added shared Player 1-4 Controller Router.
#   2026-09-19 - Added the dependency-free interactive assignment wizard.
# Full history: docs/CHANGELOG.md and Git history.

"""Versioned controller routing for RetroPie, Recalbox, and Batocera."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import select
import socket
import struct
import subprocess
import threading
import time
import secrets
import urllib.request
from pathlib import Path
from typing import Any

from .game_registry import atomic_write
from .profile_control import read_token, sign_message, verify_message
from .merged_gamepad import (
    AXIS_CODES, BUTTON_NAMES, DIRECTION_NAMES, ANALOG_NAMES,
    CANONICAL_AXIS_INDEX, CANONICAL_BUTTON_INDEX, MERGED_RETROARCH_BINDINGS,
    controller_candidates, find_saved_controller, input_devices,
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
PROTOCOL = "virtualglove-inputs/1"
MAX_REQUEST = 262144


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


def validate_config(data: object) -> dict[str, Any]:
    """Validate and normalize one complete router document."""
    if not isinstance(data, dict) or set(data) - {"format", "platform", "players", "virtualglove_player"}:
        raise ValueError("Invalid Controller Router configuration.")
    if data.get("format") != FORMAT:
        raise ValueError("Unsupported Controller Router configuration version.")
    if data.get("platform") not in SUPPORTED_PLATFORMS:
        raise ValueError("Choose RetroPie, Recalbox, or Batocera.")
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
            "virtualglove_player": data.get("virtualglove_player")}


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
                              "virtualglove_player": 1})
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
        results.append({"id": public_id, "name": item["name"],
                        "identity_suffix": public_id[-6:], "connected": True,
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
                                "assigned_player": entry["player"], "suggested_player": None})
    return results


def test_activity(es_inputs: Path, duration_ms: int = 500,
                  *, sys_root: Path = Path("/sys/class/input"),
                  dev_root: Path = Path("/dev/input")) -> dict[str, list[str]]:
    """Observe a short, non-grabbing controller window and return logical controls only."""
    duration_ms = max(0, min(1000, int(duration_ms)))
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
        buttons = set().union(*(state.buttons for state in self.physical.values()),
                              self.virtual.buttons)
        if self.player != 1:
            buttons.discard("hotkey")
        physical_movement = any(value for state in self.physical.values()
                                for value in state.axes.values())
        axes = {}
        for axis in AXIS_CODES:
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


def fceumm_running(proc_root: Path = Path("/proc")) -> bool:
    """Recognize only a RetroArch process that loaded FCEUmm."""
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return False
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
        for index, value in enumerate(args[:-1]):
            if value in ("-L", "--libretro") and "fceumm" in Path(args[index + 1]).name.casefold():
                return True
    return False


class ControllerRouterDevice:
    """Own Player 1-4 outputs and dynamically reconnect their physical sources."""
    EVENT = struct.Struct("llHHi")

    def __init__(self, config_path: Path, retroarch_config: Path,
                 socket_path: Path | None = None, *, sinks: dict[int, Any] | None = None,
                 global_config: Path | None = None,
                 proc_root: Path = Path("/proc"), sys_root: Path = Path("/sys/class/input"),
                 udev_root: Path = Path("/run/udev/data"), dev_root: Path = Path("/dev/input")) -> None:
        self.config_path, self.config = Path(config_path), load_config(config_path)
        self.retroarch_config, self.proc_root = Path(retroarch_config), proc_root
        self.global_config = Path(global_config) if global_config else None
        self.sys_root, self.udev_root, self.dev_root = sys_root, udev_root, dev_root
        self.players = {player: PlayerState(player) for player in enabled_players(self.config)}
        self.sinks = sinks if sinks is not None else {player: UInputMergedGamepad(
            name=output_name(player), product=DEVICE_PRODUCT_BASE + player)
            for player in self.players}
        self.descriptors: dict[int, dict[str, Any]] = {}
        self.socket_path, self.socket = socket_path, None
        self.virtual_updated_at = 0.0
        self.config_revision = revision(self.config)
        self.config_checked_at = 0.0
        self.installed_indexes: dict[int, int] = {}
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
            raise
        self.thread = threading.Thread(target=self._run, name="virtualglove-controller-router", daemon=True)
        self.thread.start()

    def _install_indexes(self) -> None:
        """Wait for every output and atomically update the managed settings."""
        for _attempt in range(40):
            indexes = output_indexes(list(self.players), self.sys_root, self.udev_root)
            if len(indexes) == len(self.players):
                current = self.retroarch_config.read_text() if self.retroarch_config.exists() else ""
                global_path = self.global_config or self.retroarch_config.with_name("retroarchcustom.cfg")
                updated = merge_retroarch_config(current, self.config, indexes,
                    global_path.read_text() if global_path.exists() else "")
                atomic_write(self.retroarch_config, updated, 0o644)
                self.installed_indexes = indexes
                return
            time.sleep(0.05)
        raise RuntimeError("Controller Router outputs did not appear in /sys/class/input")

    def _set_active(self, active: bool) -> None:
        """Grab or release physical sources across an FCEUmm transition."""
        for fd, record in list(self.descriptors.items()):
            if record["grabbed"] != active:
                try:
                    fcntl.ioctl(record["fd"], EVIOCGRAB, int(active))
                    record["grabbed"] = active
                except OSError:
                    self._drop(fd)
        for state in self.players.values():
            state.active = active
        self._publish()

    def _reload_config(self, updated: dict[str, Any]) -> None:
        """Rebuild outputs only while idle after an atomic configuration save."""
        previous, previous_revision = self.config, self.config_revision
        for fd in list(self.descriptors):
            self._drop(fd)
        for sink in self.sinks.values():
            sink.close()
        try:
            self.config = updated
            self.players = {player: PlayerState(player) for player in enabled_players(updated)}
            self.sinks = {player: UInputMergedGamepad(
                name=output_name(player), product=DEVICE_PRODUCT_BASE + player)
                for player in self.players}
            self.config_revision = revision(updated)
            self._install_indexes()
        except Exception:
            for sink in self.sinks.values():
                sink.close()
            self.config, self.config_revision = previous, previous_revision
            self.players = {player: PlayerState(player) for player in enabled_players(previous)}
            self.sinks = {player: UInputMergedGamepad(
                name=output_name(player), product=DEVICE_PRODUCT_BASE + player)
                for player in self.players}
            self._install_indexes()
            raise

    def _publish(self) -> None:
        """Write all merged player states to their independent outputs."""
        for player, state in self.players.items():
            self.sinks[player].write(*state.desired())

    def _saved_sources(self) -> list[tuple[int, dict[str, Any]]]:
        """Flatten configured physical sources with their player slot."""
        return [(entry["player"], source) for entry in self.config["players"]
                for source in entry["sources"]]

    def _discover(self) -> None:
        """Reconnect saved identities without depending on event numbering."""
        candidates = input_devices(self.sys_root, self.dev_root)
        connected_ids = {record["source_id"] for record in self.descriptors.values()}
        for player, saved in self._saved_sources():
            if saved["id"] in connected_ids:
                continue
            candidate = find_saved_controller(saved, candidates)
            if candidate is None:
                continue
            joy_fd = event_fd = None
            try:
                joy_fd = os.open(candidate["joystick"], os.O_RDONLY | os.O_NONBLOCK)
                mapping = translate_es_mapping(saved["mapping"], joy_fd)
                event_fd = os.open(candidate["event"], os.O_RDONLY | os.O_NONBLOCK)
                source = self.players[player].physical.setdefault(saved["id"], SourceState())
                mapper = PhysicalMapper(mapping, _MapperState(source), input_axis_ranges(event_fd, mapping))
                active = self.players[player].active
                if active:
                    fcntl.ioctl(event_fd, EVIOCGRAB, 1)
                self.descriptors[event_fd] = {"fd": event_fd, "source_id": saved["id"],
                                              "player": player, "source": source,
                                              "mapper": mapper, "grabbed": active}
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
        state = self.players[player].virtual; state.release()
        buttons = incoming.get("buttons", {})
        for name in ("a", "b", "start", "select"):
            if buttons.get(name): state.buttons.add(name)
        if buttons.get("glove_zap"): state.buttons.add("r2")
        dpad, axes = incoming.get("dpad", {}), incoming.get("axes", {})
        state.set_axis("hat_x", int(bool(dpad.get("right"))) - int(bool(dpad.get("left"))))
        state.set_axis("hat_y", int(bool(dpad.get("down"))) - int(bool(dpad.get("up"))))
        for target, source in (("lx", "x"), ("ly", "y"), ("rx", "roll"), ("ry", "z")):
            state.set_axis(target, max(-32767, min(32767, int(axes.get(source, 0)))))
        self.virtual_updated_at = time.monotonic(); self._publish()

    def _run(self) -> None:
        """Monitor FCEUmm, configuration, hot-plug, and source events."""
        active = False
        while not self.stop.is_set():
            with self.lock:
                now_active = fceumm_running(self.proc_root)
                if now_active != active:
                    if now_active and output_indexes(list(self.players), self.sys_root,
                                                     self.udev_root) != self.installed_indexes:
                        self._install_indexes()
                    active = now_active; self._set_active(active)
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
                                            self.udev_root) != self.installed_indexes:
                            self._install_indexes()
                    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                        pass
                    self.config_checked_at = time.monotonic()
                self._discover()
            sources = list(self.descriptors)
            if self.socket is not None: sources.append(self.socket)
            if not sources:
                self.stop.wait(0.2); continue
            try:
                ready, _, _ = select.select(sources, [], [], 0.1)
            except (OSError, ValueError):
                continue
            with self.lock:
                if self.socket is not None and self.socket in ready:
                    try:
                        payload = self.socket.recv(8193)
                        incoming = virtual_state(json.loads(payload)) if len(payload) <= 8192 else None
                        if incoming is not None: self._virtual(incoming)
                    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
                        pass
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

    def close(self) -> None:
        """Neutralize and close every router-owned resource."""
        self.stop.set(); self.thread.join(timeout=2)
        for fd in list(self.descriptors): self._drop(fd)
        if self.socket is not None:
            self.socket.close()
            try: self.socket_path.unlink()
            except FileNotFoundError: pass
        for sink in self.sinks.values(): sink.close()


def output_name(player: int) -> str:
    """Return the stable uinput name for a bounded player slot."""
    if player not in (1, 2, 3, 4):
        raise ValueError("player must be between 1 and 4")
    return DEVICE_NAME.format(player)


def output_indexes(players: list[int], sys_root: Path = Path("/sys/class/input"),
                   udev_root: Path = Path("/run/udev/data")) -> dict[int, int]:
    """Resolve current RetroArch indexes without persisting enumeration numbers."""
    found = {}
    for player in players:
        index = merged_joypad_index(sys_root, udev_root, output_name(player))
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


def merge_retroarch_config(text: str, config: dict[str, Any], indexes: dict[int, int],
                           global_config: str = "") -> str:
    """Replace only the router-managed NES/FCEUmm block for enabled slots."""
    begin, end = "# VirtualGlove Controller Router", "# End VirtualGlove Controller Router"
    retired_begin, retired_end = "# VirtualGlove merged Player 1", "# End VirtualGlove merged Player 1"
    output, inside = [], False
    for line in text.splitlines():
        if line.strip() in (begin, retired_begin):
            inside = True
            continue
        if inside:
            if line.strip() in (end, retired_end):
                inside = False
            continue
        if line.strip() != "# VirtualGlove Player 1 keyboard merge":
            output.append(line)
    while output and not output[-1]:
        output.pop()
    output.extend(["", begin])
    by_player = {entry["player"]: entry for entry in config["players"]}
    for player in enabled_players(config):
        if player not in indexes:
            raise ValueError("Merged Player %d is not available." % player)
        output.append('input_player%d_joypad_index = "%d"' % (player, indexes[player]))
        output.extend('%s = "%s"' % item for item in _player_bindings(player).items())
        if player == 1 and by_player.get(1, {}).get("sources"):
            hotkeys = platform_hotkey_bindings(
                {**by_player[1]["sources"][0], "platform": config["platform"]}, global_config)
            output.extend('%s = "%s"' % item for item in hotkeys.items()
                          if item[0] not in MERGED_RETROARCH_BINDINGS)
    output.append(end)
    return "\n".join(output).lstrip("\n") + "\n"


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
        self.activity_check = activity_check or fceumm_running
        self.activate = activate
        self.lock = threading.Lock()

    def _default(self) -> dict[str, Any]:
        """Return an inactive configuration for an unconfigured platform."""
        return {"format": FORMAT, "platform": self.platform, "players": [],
                "virtualglove_player": None}

    def read(self) -> dict[str, Any]:
        """Return configuration, revision, rollback state, and inventory."""
        config = load_config(self.path) if self.path.exists() else self._default()
        return {"config": config, "revision": revision(config),
                "has_backup": self.backup.exists(),
                "inventory": inventory(self.es_inputs, config)}

    def _materialize(self, proposed: object) -> dict[str, Any]:
        """Replace public source IDs with authoritative saved mappings."""
        if not isinstance(proposed, dict):
            raise ValueError("Controller Router configuration is missing.")
        candidates = {item["id"]: item for item in controller_candidates(self.es_inputs)}
        if self.path.exists():
            connected = list(candidates.values())
            for entry in load_config(self.path)["players"]:
                for source in entry["sources"]:
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
        return validate_config({"format": FORMAT, "platform": self.platform, "players": players,
                                "virtualglove_player": proposed.get("virtualglove_player")})

    def operate(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Perform one bounded revision-checked router operation."""
        with self.lock:
            current = self.read()
            if operation in ("read", "inventory"):
                return current
            if operation == "check":
                config = current["config"]
                connected = {item["id"] for item in current["inventory"]}
                missing = [source["id"] for entry in config["players"] for source in entry["sources"]
                           if source["id"] not in connected]
                activity = test_activity(self.es_inputs, payload.get("watch_ms", 0))
                return {**current, "enabled_players": enabled_players(config),
                        "missing_sources": missing, "activity": activity,
                        "safe": not missing}
            if operation not in ("save", "rollback"):
                raise ValueError("Unsupported Controller Router operation.")
            if self.activity_check():
                raise ValueError("Close the running FCEUmm game before changing controller assignments.")
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
                        self.path.unlink(missing_ok=True)
                    raise ValueError("Assignments were not activated; the previous configuration was restored.")
            return self.read()


class RouterService:
    """Authenticate bounded Controller Router operations with the paired key."""
    def __init__(self, store: RouterStore, token_file: Path, clock=time.monotonic) -> None:
        self.store, self.token_file, self.clock = store, Path(token_file), clock
        self.challenges: dict[str, float] = {}

    def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        """Authenticate one challenge or signed Router operation."""
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            raise ValueError("Unsupported Controller Router protocol.")
        token, now = read_token(None, self.token_file), self.clock()
        self.challenges = {key: expiry for key, expiry in self.challenges.items() if expiry > now}
        if request.get("operation") == "challenge":
            if len(self.challenges) >= 64:
                raise ValueError("Controller Router is busy. Retry shortly.")
            challenge = secrets.token_hex(32)
            self.challenges[challenge] = now + 15
            return sign_message({"protocol": PROTOCOL, "challenge": challenge,
                                 "request_id": request.get("request_id"), "ok": True}, token)
        if not verify_message(request, token):
            raise ValueError("Pairing authentication failed.")
        challenge = request.get("challenge")
        if not isinstance(challenge, str) or self.challenges.pop(challenge, 0) <= now:
            raise ValueError("Expired or already used request. Retry the operation.")
        response = {"protocol": PROTOCOL, "request_id": request.get("request_id"),
                    "challenge": challenge}
        try:
            response.update(ok=True, result=self.store.operate(request.get("operation", ""), request))
        except ValueError as exc:
            response.update(ok=False, error=str(exc))
        except (OSError, UnicodeError, json.JSONDecodeError):
            response.update(ok=False, error="Cannot inspect or save Controller Router settings.")
        return sign_message(response, token)


def router_request(settings: dict[str, Any], operation: str,
                   payload: dict[str, Any] | None = None, port: int = 55358) -> dict[str, Any]:
    """Call the paired console's fixed-purpose Controller Router endpoint."""
    from .resolver import resolve_ipv4
    token, host = settings.get("token", ""), settings.get("receiver", "")
    if not host or len(token) < 16:
        raise ValueError("Configure and pair your console before opening Controller Router.")
    url = "http://%s:%d/inputs" % (resolve_ipv4(host), port)
    request_id = secrets.token_hex(16)

    def exchange(data: dict[str, Any]) -> dict[str, Any]:
        """Send and authenticate one correlated protocol message."""
        request = urllib.request.Request(url, data=json.dumps(data).encode(),
                                         headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=4) as response:
                body = response.read(MAX_REQUEST + 1)
            if len(body) > MAX_REQUEST:
                raise ValueError("Controller Router response is too large.")
            result = json.loads(body)
        except (OSError, ValueError) as exc:
            raise ValueError("Cannot reach Controller Router. Check the paired console and its VirtualGlove installation.") from exc
        if (not isinstance(result, dict) or result.get("protocol") != PROTOCOL
                or result.get("request_id") != request_id or not verify_message(result, token)):
            raise ValueError("Controller Router authentication failed. Check pairing.")
        return result

    challenge = exchange({"protocol": PROTOCOL, "operation": "challenge",
                          "request_id": request_id})["challenge"]
    data = dict(payload or {})
    data.update(protocol=PROTOCOL, operation=operation, request_id=request_id, challenge=challenge)
    response = exchange(sign_message(data, token))
    if response.get("challenge") != challenge:
        raise ValueError("Controller Router returned the wrong challenge.")
    if not response.get("ok"):
        raise ValueError(response.get("error", "Controller Router operation failed."))
    return response["result"]


def _paths(platform: str) -> tuple[Path, Path, Path, Path]:
    """Return fixed configuration paths for one supported console."""
    if platform == "recalbox":
        root = Path("/recalbox/share/system/virtualglove")
        retroarch = Path("/recalbox/share/system/configs/retroarch")
        return (root / "data/controller-router.json",
                Path("/recalbox/share/system/.emulationstation/es_input.cfg"),
                retroarch / "config/FCEUmm/FCEUmm.cfg",
                retroarch / "retroarchcustom.cfg")
    if platform == "batocera":
        root = Path("/userdata/system/virtualglove")
        retroarch = Path("/userdata/system/configs/retroarch")
        return (root / "data/controller-router.json",
                Path("/userdata/system/configs/emulationstation/es_input.cfg"),
                retroarch / "config/FCEUmm/FCEUmm.cfg",
                retroarch / "retroarchcustom.cfg")
    return (Path("/etc/virtualglove/controller-router.json"),
            Path("/opt/retropie/configs/all/emulationstation/es_input.cfg"),
            Path("/opt/retropie/configs/all/retroarch/config/FCEUmm/FCEUmm.cfg"),
            Path("/opt/retropie/configs/nes/retroarchcustom.cfg"))


def _assignment_label(player: int | None) -> str:
    """Return the compact label used by the terminal assignment table."""
    return "Player %d" % player if player else "Unassigned"


def _wizard_screen(state: dict[str, Any], assignments: dict[str, int | None],
                   virtual_player: int | None) -> str:
    """Render one dependency-free Controller Router terminal screen."""
    rows = []
    for index, source in enumerate(state["inventory"], 1):
        name = source["name"][:31]
        identity = source.get("identity_suffix", source["id"][-6:])
        connected = "Connected" if source.get("connected") else "Unavailable"
        rows.append("| %2d  %-31s %-10s %-11s %-11s |" % (
            index, name, identity, _assignment_label(assignments.get(source["id"])), connected))
    if not rows:
        rows.append("|     No configured EmulationStation controllers found.                 |")
    lines = [
        "+------------------ VirtualGlove Controller Router -------------------+",
        "| Assign configured controllers to the merged FCEUmm players.          |",
        "+-----------------------------------------------------------------------+",
        "| No. Controller                      ID         Assignment  Status      |",
        "+-----------------------------------------------------------------------+",
        *rows,
        "+-----------------------------------------------------------------------+",
        "| VirtualGlove: %-54s |" % _assignment_label(virtual_player),
        "| [1-%d] Assign controller  [V] VirtualGlove  [T] Test controls          |" % max(1, len(rows)),
        "| [S] Save and verify      [R] Roll back     [Q] Quit                   |",
        "+-----------------------------------------------------------------------+",
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
        if len(output_indexes(players)) == len(players):
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
            output_fn("Press a button or direction on a controller...")
            result = store.operate("check", {"watch_ms": 1500})
            if result["activity"]:
                names = {item["id"]: item["name"] for item in result["inventory"]}
                for identity, controls in result["activity"].items():
                    output_fn("PASS  %s: %s" % (names.get(identity, identity[-6:]),
                                                ", ".join(controls)))
            else:
                output_fn("ACTION  No control was pressed during the test.")
            if result["missing_sources"]:
                output_fn("ACTION  %d assigned controller(s) are unavailable." %
                          len(result["missing_sources"]))
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
                                             "apply", "rollback", "serve"))
    parser.add_argument("--platform", choices=SUPPORTED_PLATFORMS,
                        help="Console platform; detected automatically when omitted")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--document", type=Path, help="JSON assignment document for configure")
    parser.add_argument("--socket", type=Path)
    args = parser.parse_args()
    platform = args.platform or detect_platform()
    default_config, es_inputs, retroarch, global_config = _paths(platform)

    def activate_retropie() -> None:
        """Start RetroPie's opt-in Router after its first local wizard save."""
        if platform != "retropie":
            return
        subprocess.run(("systemctl", "enable", "--now",
                        "virtualglove-controller-router.service"), check=True)
        subprocess.run(("systemctl", "restart", "virtualglove-receiver.service"), check=True)

    store = RouterStore(args.config or default_config, platform, es_inputs, retroarch,
                        activate=activate_retropie if platform == "retropie" else None)
    if args.command == "setup":
        return run_setup_wizard(store)
    if args.command == "serve":
        if args.socket is None:
            parser.error("serve requires --socket")
        device = ControllerRouterDevice(args.config or default_config, retroarch, args.socket,
                                        global_config=global_config)
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
        config = store.read()["config"]
        if platform == "retropie":
            was_active = subprocess.run(
                ("systemctl", "is-active", "--quiet", "virtualglove-controller-router.service"),
                check=False).returncode == 0
            subprocess.run(("systemctl", "enable", "--now",
                            "virtualglove-controller-router.service"), check=True)
            for _attempt in range(40):
                if len(output_indexes(enabled_players(config))) == len(enabled_players(config)):
                    break
                time.sleep(0.05)
        indexes = output_indexes(enabled_players(config))
        current = retroarch.read_text() if retroarch.exists() else ""
        updated = merge_retroarch_config(current, config, indexes,
                                          global_config.read_text() if global_config.exists() else "")
        atomic_write(retroarch, updated, 0o644)
        if platform == "retropie" and not was_active:
            subprocess.run(("systemctl", "restart", "virtualglove-receiver.service"), check=True)
        print("Controller Router assignments applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
