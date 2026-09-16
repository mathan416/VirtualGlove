# Project: VirtualGlove
# File: src/powerglove_vision/merged_gamepad.py
# Purpose: Merge one configured Linux Player 1 controller with VirtualGlove.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added Recalbox/Batocera merged Player 1 input.
# Full history: docs/CHANGELOG.md and Git history.

"""Dependency-free physical-controller discovery and merged uinput output."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import select
import socket
import struct
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable


DEVICE_NAME = "VirtualGlove Merged Player 1"
FORMAT = 1
VIRTUAL_TIMEOUT_SECONDS = 0.5
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0
BUS_VIRTUAL = 0x06
PHYSICAL_AXIS_DEADZONE = 4096

# Canonical Linux gamepad layout. Its ordered keys intentionally match the
# RetroArch indices in MERGED_RETROARCH_BINDINGS below.
BUTTON_CODES = {
    "a": 304, "b": 305, "c": 306, "x": 307, "y": 308, "z": 309,
    "l1": 310, "r1": 311, "l2": 312, "r2": 313,
    "select": 314, "start": 315, "hotkey": 316, "l3": 317, "r3": 318,
}
AXIS_CODES = {"lx": 0, "ly": 1, "rx": 3, "ry": 4, "hat_x": 16, "hat_y": 17}
BUTTON_NAMES = {
    "a": "a", "b": "b", "x": "x", "y": "y",
    "l1": "l1", "r1": "r1",
    "pageup": "l1", "pagedown": "r1", "l2": "l2", "r2": "r2",
    "l3": "l3", "r3": "r3",
    # Accept descriptive aliases written by some EmulationStation builds.
    "leftshoulder": "l1", "rightshoulder": "r1",
    "lefttrigger": "l2", "righttrigger": "r2",
    "select": "select", "start": "start", "hotkey": "hotkey",
    "leftthumb": "l3", "rightthumb": "r3",
}
CANONICAL_BUTTON_INDEX = {name: index for index, name in enumerate(BUTTON_CODES)}
CANONICAL_AXIS_INDEX = {"lx": 0, "ly": 1, "rx": 2, "ry": 3}
DIRECTION_NAMES = {"left": ("hat_x", -1), "right": ("hat_x", 1),
                   "up": ("hat_y", -1), "down": ("hat_y", 1)}
ANALOG_NAMES = {
    "joystick1left": ("lx", -1), "joystick1up": ("ly", -1),
    "joystick2left": ("rx", -1), "joystick2up": ("ry", -1),
    # Accept descriptive aliases used by a few downstream frontends.
    "leftanalogleft": ("lx", -1), "leftanalogup": ("ly", -1),
    "rightanalogleft": ("rx", -1), "rightanalogup": ("ry", -1),
}

MERGED_RETROARCH_BINDINGS = {
    "input_player1_a_btn": "0", "input_player1_b_btn": "1",
    "input_player1_x_btn": "3", "input_player1_y_btn": "4",
    "input_player1_l_btn": "6", "input_player1_r_btn": "7",
    "input_player1_l2_btn": "8", "input_player1_r2_btn": "9",
    "input_player1_select_btn": "10", "input_player1_start_btn": "11",
    "input_enable_hotkey_btn": "12",
    "input_player1_l3_btn": "13", "input_player1_r3_btn": "14",
    "input_player1_left_btn": "h0left", "input_player1_right_btn": "h0right",
    "input_player1_up_btn": "h0up", "input_player1_down_btn": "h0down",
    "input_player1_l_x_minus_axis": "-0", "input_player1_l_x_plus_axis": "+0",
    "input_player1_l_y_minus_axis": "-1", "input_player1_l_y_plus_axis": "+1",
    "input_player1_r_x_minus_axis": "-2", "input_player1_r_x_plus_axis": "+2",
    "input_player1_r_y_minus_axis": "-3", "input_player1_r_y_plus_axis": "+3",
}
OLD_KEYBOARD_BINDINGS = {
    "input_player1_a": "x", "input_player1_b": "z",
    "input_player1_start": "enter", "input_player1_select": "rshift",
    "input_player1_up": "up", "input_player1_down": "down",
    "input_player1_left": "left", "input_player1_right": "right",
}


def _ioc(direction: int, kind: int, number: int, size: int) -> int:
    """Build one Linux ioctl request number."""
    return (direction << 30) | (size << 16) | (kind << 8) | number


def _iow(kind: int, number: int, size: int = 4) -> int:
    """Build one write-direction Linux ioctl request number."""
    return _ioc(1, kind, number, size)


def _ior(kind: int, number: int, size: int) -> int:
    """Build one read-direction Linux ioctl request number."""
    return _ioc(2, kind, number, size)


UI_SET_EVBIT = _iow(ord("U"), 100)
UI_SET_KEYBIT = _iow(ord("U"), 101)
UI_SET_ABSBIT = _iow(ord("U"), 103)
UI_DEV_CREATE = _ioc(0, ord("U"), 1, 0)
UI_DEV_DESTROY = _ioc(0, ord("U"), 2, 0)
ABS_INFO = struct.Struct("iiiiii")
JS_AXIS_MAP_SIZE = 0x40
JS_BUTTON_MAP_SIZE = 0x200
JSIOCGAXES = _ior(ord("j"), 0x11, 1)
JSIOCGBUTTONS = _ior(ord("j"), 0x12, 1)
JSIOCGAXMAP = _ior(ord("j"), 0x32, JS_AXIS_MAP_SIZE)
JSIOCGBTNMAP = _ior(ord("j"), 0x34, JS_BUTTON_MAP_SIZE * 2)


def _text(path: Path) -> str:
    """Read a small sysfs text value, returning empty text when unavailable."""
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _valid_input_code(kind: str, code: int) -> bool:
    """Bound saved SDL indices and translated Linux input codes."""
    return ((kind == "button" and 0 <= code <= 0x2FF) or
            (kind in ("axis", "hat") and 0 <= code <= 0x3F))


def input_devices(sys_root: Path = Path("/sys/class/input"),
                  dev_root: Path = Path("/dev/input")) -> list[dict]:
    """Return stable descriptions of connected non-VirtualGlove event devices."""
    devices = []
    for event in sorted(sys_root.glob("event*")):
        base = event / "device"
        name = _text(base / "name")
        if not name or name.startswith("VirtualGlove"):
            continue
        capabilities = _text(base / "capabilities/key")
        if not capabilities or not any(value != "0" for value in capabilities.split()):
            continue
        identity = {
            "name": name,
            "vendor": _text(base / "id/vendor"),
            "product": _text(base / "id/product"),
            "version": _text(base / "id/version"),
            "uniq": _text(base / "uniq"),
            "phys": _text(base / "phys"),
            "event": str(dev_root / event.name),
        }
        try:
            device_path = base.resolve()
            joystick = next(
                item for item in sorted(sys_root.glob("js*"))
                if (item / "device").resolve() == device_path)
            identity["joystick"] = str(dev_root / joystick.name)
        except (OSError, StopIteration):
            # EmulationStation stores SDL indices rather than evdev codes. A
            # sibling joystick node is required to translate them safely.
            continue
        stable_keys = (("name", "vendor", "product", "version", "uniq")
                       if identity["uniq"] else
                       ("name", "vendor", "product", "version", "phys"))
        stable = "\0".join(identity[key] for key in stable_keys)
        identity["id"] = hashlib.sha256(stable.encode()).hexdigest()[:16]
        devices.append(identity)
    return devices


def parse_es_inputs(path: Path) -> list[dict]:
    """Read configured joystick mappings without trusting XML paths or commands."""
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError):
        return []
    results = []
    for node in root.findall(".//inputConfig"):
        if node.get("type", "").casefold() not in ("joystick", "gamepad"):
            continue
        name = node.get("deviceName", "").strip()
        guid = node.get("deviceGUID", "").strip().casefold()
        if not name:
            continue
        mappings = []
        for item in node.findall("input"):
            logical = item.get("name", "").strip().casefold()
            kind = item.get("type", "").strip().casefold()
            # Current Batocera/Recalbox files persist SDL's device-local
            # index as ``id``. Some generated catalogs also include the Linux
            # event ``code``; the SDL index remains the stable mapping input.
            code = item.get("id", item.get("code"))
            value = item.get("value", "1")
            if logical not in BUTTON_NAMES and logical not in DIRECTION_NAMES and logical not in ANALOG_NAMES:
                continue
            if kind not in ("button", "axis", "hat") or code is None:
                continue
            try:
                parsed_code, parsed_value = int(code), int(value)
                if not _valid_input_code(kind, parsed_code):
                    continue
                mappings.append({"name": logical, "type": kind,
                                 "code": parsed_code, "value": parsed_value})
            except ValueError:
                continue
        if mappings:
            results.append({"name": name, "guid": guid, "mapping": mappings})
    return results


def controller_candidates(es_inputs: Path, sys_root: Path = Path("/sys/class/input"),
                          dev_root: Path = Path("/dev/input")) -> list[dict]:
    """Match configured EmulationStation gamepads to connected event devices."""
    configured = parse_es_inputs(es_inputs)
    candidates = []
    for device in input_devices(sys_root, dev_root):
        matches = [item for item in configured if item["name"] == device["name"]]
        unique = {json.dumps(item, sort_keys=True): item for item in matches}
        if len(unique) == 1:
            selected = next(iter(unique.values()))
            candidate = dict(device)
            candidate.update({"guid": selected["guid"], "mapping": selected["mapping"]})
            candidates.append(candidate)
    return candidates


def save_controller(path: Path, candidate: dict, platform: str) -> dict:
    """Persist only bounded device identity and controller mapping data."""
    data = {"format": FORMAT, "platform": platform,
            **{key: candidate.get(key, "") for key in
               ("id", "name", "guid", "vendor", "product", "version", "uniq", "phys")},
            "mapping": candidate["mapping"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(str(temporary), str(path))
    return data


def load_controller(path: Path) -> dict:
    """Load and strictly validate one saved merged-controller record."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("unsupported merged Player 1 controller configuration")
    if data.get("platform") not in ("recalbox", "batocera"):
        raise ValueError("invalid merged Player 1 platform")
    for key in ("id", "name", "guid", "vendor", "product", "version", "uniq", "phys"):
        if not isinstance(data.get(key, ""), str) or len(data.get(key, "")) > 512:
            raise ValueError("invalid merged Player 1 identity")
    if not data.get("name") or not isinstance(data.get("mapping"), list):
        raise ValueError("invalid merged Player 1 controller configuration")
    if not 1 <= len(data["mapping"]) <= 64:
        raise ValueError("invalid merged Player 1 mapping")
    for item in data["mapping"]:
        if (not isinstance(item, dict) or set(item) != {"name", "type", "code", "value"} or
                (item.get("name") not in BUTTON_NAMES and
                 item.get("name") not in DIRECTION_NAMES and
                 item.get("name") not in ANALOG_NAMES) or
                item.get("type") not in ("button", "axis", "hat") or
                isinstance(item.get("code"), bool) or not isinstance(item.get("code"), int) or
                not _valid_input_code(item.get("type"), item["code"]) or
                isinstance(item.get("value"), bool) or not isinstance(item.get("value"), int) or
                not -0x8000 <= item["value"] <= 0x7FFF):
            raise ValueError("invalid merged Player 1 mapping")
    return data


def virtual_state(data: object) -> dict | None:
    """Return a bounded controller state or reject a malformed local datagram."""
    if not isinstance(data, dict):
        return None
    dpad, buttons, axes = data.get("dpad", {}), data.get("buttons", {}), data.get("axes", {})
    if not all(isinstance(item, dict) for item in (dpad, buttons, axes)):
        return None
    if any(key not in ("up", "down", "left", "right") or not isinstance(value, bool)
           for key, value in dpad.items()):
        return None
    if any(key not in ("a", "b", "start", "select", "glove_zap") or
           not isinstance(value, bool) for key, value in buttons.items()):
        return None
    if any(key not in ("x", "y", "z", "roll") or isinstance(value, bool) or
           not isinstance(value, int) or not -32767 <= value <= 32767
           for key, value in axes.items()):
        return None
    return {"dpad": dict(dpad), "buttons": dict(buttons), "axes": dict(axes)}


def merged_payload(state: dict) -> dict:
    """Project a validated controller state onto the merger's smaller contract."""
    allowed = {
        "dpad": ("up", "down", "left", "right"),
        "buttons": ("a", "b", "start", "select", "glove_zap"),
        "axes": ("x", "y", "z", "roll"),
    }
    return {
        group: {key: values[key] for key in keys if key in values}
        for group, keys in allowed.items()
        for values in (state.get(group, {}),)
    }


def input_axis_ranges(descriptor: int, mapping: list[dict]) -> dict[int, tuple[int, int, int]]:
    """Read physical stick ranges so arbitrary evdev scales become canonical."""
    ranges = {}
    for item in mapping:
        if item["name"] not in ANALOG_NAMES or item["code"] in ranges:
            continue
        buffer = bytearray(ABS_INFO.size)
        try:
            fcntl.ioctl(descriptor, _ior(ord("E"), 0x40 + item["code"], ABS_INFO.size),
                        buffer, True)
            _value, minimum, maximum, _fuzz, flat, _resolution = ABS_INFO.unpack(buffer)
            if minimum < maximum:
                ranges[item["code"]] = (minimum, maximum, max(0, flat))
        except OSError:
            pass
    return ranges


def translate_es_mapping(mapping: list[dict], joystick_descriptor: int) -> list[dict]:
    """Translate saved SDL indices into the selected controller's evdev codes."""
    axis_count = bytearray(1)
    button_count = bytearray(1)
    axes = bytearray(JS_AXIS_MAP_SIZE)
    buttons = bytearray(JS_BUTTON_MAP_SIZE * 2)
    fcntl.ioctl(joystick_descriptor, JSIOCGAXES, axis_count, True)
    fcntl.ioctl(joystick_descriptor, JSIOCGBUTTONS, button_count, True)
    fcntl.ioctl(joystick_descriptor, JSIOCGAXMAP, axes, True)
    fcntl.ioctl(joystick_descriptor, JSIOCGBTNMAP, buttons, True)
    button_codes = struct.unpack("%dH" % JS_BUTTON_MAP_SIZE, buttons)
    translated = []
    for item in mapping:
        output = dict(item)
        if item["type"] == "button":
            if item["code"] >= button_count[0] or not button_codes[item["code"]]:
                continue
            output["code"] = button_codes[item["code"]]
        elif item["type"] == "axis":
            if item["code"] >= axis_count[0]:
                continue
            output["code"] = axes[item["code"]]
        else:
            if item["name"] not in DIRECTION_NAMES or item["code"] > 3:
                continue
            horizontal = item["name"] in ("left", "right")
            output["type"] = "axis"
            output["code"] = 16 + item["code"] * 2 + int(not horizontal)
            output["value"] = DIRECTION_NAMES[item["name"]][1]
        if _valid_input_code(output["type"], output["code"]):
            translated.append(output)
    if not translated:
        raise ValueError("the selected Player 1 mapping has no usable controls")
    return translated


def choose_controller(candidates: list[dict], requested: str | None = None,
                      input_fn: Callable[[str], str] = input) -> dict:
    """Choose one physical Player 1 explicitly when discovery is ambiguous."""
    if requested:
        matches = [item for item in candidates if item["id"] == requested]
        if len(matches) != 1:
            raise ValueError("--player1-device does not identify one configured connected gamepad")
        return matches[0]
    if len(candidates) == 1:
        print("Using physical Player 1: " + candidates[0]["name"])
        return candidates[0]
    if not candidates:
        raise ValueError("connect and configure a physical Player 1 controller before installing")
    if not os.isatty(0):
        raise ValueError("multiple gamepads found; rerun with --player1-device ID")
    print("Choose the physical controller to merge as Player 1:")
    for index, item in enumerate(candidates, 1):
        print("  %d. %s [%s]" % (index, item["name"], item["id"]))
    try:
        selected = int(input_fn("Player 1 number: ").strip())
    except ValueError as exc:
        raise ValueError("choose one listed Player 1 number") from exc
    if not 1 <= selected <= len(candidates):
        raise ValueError("choose one listed Player 1 number")
    return candidates[selected - 1]


def controller_matches(saved: dict, candidate: dict) -> bool:
    """Reconnect a saved controller without depending on its event-number path."""
    for key in ("name", "vendor", "product", "version"):
        if saved.get(key, "") != candidate.get(key, ""):
            return False
    if saved.get("uniq"):
        return saved["uniq"] == candidate.get("uniq")
    return bool(saved.get("phys")) and saved["phys"] == candidate.get("phys")


def find_saved_controller(saved: dict, candidates: list[dict]) -> dict | None:
    """Resolve a saved pad, permitting a unique non-serial pad to move USB ports."""
    exact = [item for item in candidates if controller_matches(saved, item)]
    if len(exact) == 1:
        return exact[0]
    model = [item for item in candidates if all(
        saved.get(key, "") == item.get(key, "")
        for key in ("name", "vendor", "product", "version"))]
    return model[0] if len(model) == 1 else None


def translated_hotkey_bindings(text: str, mapping: list[dict]) -> dict[str, str]:
    """Translate Recalbox's physical hotkey actions onto the canonical merger."""
    buttons: dict[int, list[str]] = {}
    axes: dict[int, dict] = {}
    for item in mapping:
        if item["type"] == "button" and item["name"] in BUTTON_NAMES:
            buttons.setdefault(item["code"], []).append(BUTTON_NAMES[item["name"]])
        elif item["type"] == "axis":
            axes[item["code"]] = item
    translated = {}
    for line in text.splitlines():
        match = re.match(r'^\s*(input_[A-Za-z0-9_]+_(?:btn|axis))\s*=\s*"?([^"#\s]+)', line)
        if not match or match.group(1).startswith("input_player"):
            continue
        setting, value = match.group(1), match.group(2)
        if setting == "input_enable_hotkey_btn":
            translated[setting] = str(CANONICAL_BUTTON_INDEX["hotkey"])
            continue
        if setting.endswith("_btn"):
            if re.fullmatch(r"h[0-3](?:left|right|up|down)", value):
                translated[setting] = value
                continue
            if not re.fullmatch(r"[0-9]+", value):
                continue
            names = [name for name in buttons.get(int(value), []) if name != "hotkey"]
            if names:
                translated[setting] = str(CANONICAL_BUTTON_INDEX[names[0]])
            continue
        axis_match = re.fullmatch(r"([+-])([0-9]+)", value)
        if not axis_match or int(axis_match.group(2)) not in axes:
            continue
        source_sign = -1 if axis_match.group(1) == "-" else 1
        item = axes[int(axis_match.group(2))]
        if item["name"] in ANALOG_NAMES:
            target, logical_direction = ANALOG_NAMES[item["name"]]
            configured_direction = -1 if item["value"] < 0 else 1
            output_sign = source_sign * logical_direction * configured_direction
            translated[setting] = ("-" if output_sign < 0 else "+") + str(
                CANONICAL_AXIS_INDEX[target])
        elif item["name"] in BUTTON_NAMES and source_sign == (-1 if item["value"] < 0 else 1):
            translated[setting] = "nul"
            translated[setting[:-5] + "_btn"] = str(
                CANONICAL_BUTTON_INDEX[BUTTON_NAMES[item["name"]]])
    return translated


def merge_retroarch_config(text: str, index: int,
                           hotkeys: dict[str, str] | None = None) -> str:
    """Replace only retired VirtualGlove keys and managed merged-device settings."""
    hotkeys = hotkeys or {}
    managed = set(MERGED_RETROARCH_BINDINGS) | {"input_player1_joypad_index"} | set(hotkeys)
    output = []
    inside_managed_block = False
    for line in text.splitlines():
        if line.strip() == "# VirtualGlove merged Player 1":
            inside_managed_block = True
            continue
        if inside_managed_block:
            if line.strip() == "# End VirtualGlove merged Player 1":
                inside_managed_block = False
            continue
        match = re.match(r"^\s*([a-zA-Z0-9_]+)\s*=\s*\"?([^\"#]*)", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            if key in managed or (key in OLD_KEYBOARD_BINDINGS and
                                  value == OLD_KEYBOARD_BINDINGS[key]):
                continue
        if line.strip() != "# VirtualGlove Player 1 keyboard merge":
            output.append(line)
    while output and not output[-1]:
        output.pop()
    output.extend(["", "# VirtualGlove merged Player 1",
                   'input_player1_joypad_index = "%d"' % index])
    output.extend('%s = "%s"' % item for item in MERGED_RETROARCH_BINDINGS.items())
    output.extend('%s = "%s"' % item for item in hotkeys.items()
                  if item[0] not in MERGED_RETROARCH_BINDINGS)
    output.append("# End VirtualGlove merged Player 1")
    return "\n".join(output).lstrip("\n") + "\n"


class MergeState:
    """Combine physical and camera state while keeping the hotkey physical-only."""

    def __init__(self) -> None:
        self.physical_buttons: set[str] = set()
        self.physical_axes = {name: 0 for name in AXIS_CODES}
        self.virtual = {}
        self.active = False

    def release_physical(self) -> None:
        """Release only controls owned by the physical source."""
        self.physical_buttons.clear()
        self.physical_axes = {name: 0 for name in AXIS_CODES}

    def desired(self) -> tuple[set[str], dict[str, int]]:
        """Return the currently merged button and axis state."""
        if not self.active:
            return set(), {name: 0 for name in AXIS_CODES}
        virtual_buttons = set()
        buttons = self.virtual.get("buttons", {})
        for name in ("a", "b", "start", "select"):
            if buttons.get(name):
                virtual_buttons.add(name)
        if buttons.get("glove_zap"):
            virtual_buttons.add("r2")
        dpad = self.virtual.get("dpad", {})
        virtual_axes = {name: 0 for name in AXIS_CODES}
        virtual_axes["hat_x"] = int(bool(dpad.get("right"))) - int(bool(dpad.get("left")))
        virtual_axes["hat_y"] = int(bool(dpad.get("down"))) - int(bool(dpad.get("up")))
        raw_axes = self.virtual.get("axes", {})
        for target, source in (("lx", "x"), ("ly", "y"), ("rx", "roll"), ("ry", "z")):
            virtual_axes[target] = max(-32767, min(32767, int(raw_axes.get(source, 0))))
        desired_axes = {}
        for name in AXIS_CODES:
            physical = self.physical_axes[name]
            desired_axes[name] = physical if physical else virtual_axes[name]
        return self.physical_buttons | virtual_buttons, desired_axes


class PhysicalMapper:
    """Translate one saved EmulationStation mapping into canonical state."""

    def __init__(self, mapping: list[dict], state: MergeState,
                 axis_ranges: dict[int, tuple[int, int, int]] | None = None) -> None:
        self.mapping = mapping
        self.state = state
        self.axis_ranges = axis_ranges or {}
        self.pressed_directions: set[str] = set()

    def _analog(self, item: dict, value: int) -> int:
        """Normalize one physical stick value and suppress ordinary center drift."""
        configured_direction = -1 if item["value"] < 0 else 1
        direction = ANALOG_NAMES[item["name"]][1]
        if item["code"] in self.axis_ranges:
            minimum, maximum, flat = self.axis_ranges[item["code"]]
            center = (minimum + maximum) / 2.0
            delta = float(value) - center
            span = (maximum - center) if delta >= 0 else (center - minimum)
            scaled = round(delta * 32767 / span) if span else 0
            normalized_flat = round(flat * 32767 / span) if span else 0
        else:
            scaled, normalized_flat = int(value), 0
        scaled = max(-32767, min(32767, scaled * direction * configured_direction))
        return 0 if abs(scaled) <= max(PHYSICAL_AXIS_DEADZONE, normalized_flat) else scaled

    def event(self, kind: int, code: int, value: int) -> None:
        """Apply one Linux input event through the saved frontend mapping."""
        for item in self.mapping:
            if item["code"] != code:
                continue
            if ((item["type"] == "button" and kind != EV_KEY) or
                    (item["type"] in ("axis", "hat") and kind != EV_ABS)):
                continue
            name = item["name"]
            if item["type"] == "button":
                active = bool(value)
            elif item["type"] == "hat":
                # EmulationStation stores SDL hat directions as bit flags:
                # up=1, right=2, down=4, left=8.
                active = bool(int(value) & int(item["value"]))
            else:
                active = value < 0 if item["value"] < 0 else value > 0
            if name in BUTTON_NAMES:
                target = BUTTON_NAMES[name]
                (self.state.physical_buttons.add if active else
                 self.state.physical_buttons.discard)(target)
            elif name in DIRECTION_NAMES:
                (self.pressed_directions.add if active else self.pressed_directions.discard)(name)
                self.state.physical_axes["hat_x"] = (
                    int("right" in self.pressed_directions) - int("left" in self.pressed_directions))
                self.state.physical_axes["hat_y"] = (
                    int("down" in self.pressed_directions) - int("up" in self.pressed_directions))
            elif name in ANALOG_NAMES:
                axis, _direction = ANALOG_NAMES[name]
                # One ES entry describes the negative side of a complete stick
                # axis. Preserve its full signed travel and honor an inverted
                # mapping rather than treating the positive half as released.
                self.state.physical_axes[axis] = self._analog(item, value)


class UInputMergedGamepad:
    """Publish the canonical merged controller without python-evdev."""

    EVENT = struct.Struct("llHHi")

    def __init__(self, path: Path = Path("/dev/uinput")) -> None:
        self.fd = os.open(str(path), os.O_WRONLY | os.O_NONBLOCK)
        self.closed = False
        self.buttons: set[str] = set()
        self.axes = {name: 0 for name in AXIS_CODES}
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            for code in BUTTON_CODES.values():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            for code in AXIS_CODES.values():
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            header = struct.pack("80sHHHHi", DEVICE_NAME.encode(), BUS_VIRTUAL,
                                 0x1209, 0x5647, 0x0100, 0)
            maximum = [0] * 64
            minimum = [0] * 64
            flat = [0] * 64
            for name, code in AXIS_CODES.items():
                if name.startswith("hat"):
                    maximum[code], minimum[code] = 1, -1
                else:
                    maximum[code], minimum[code], flat[code] = 32767, -32767, 2048
            os.write(self.fd, header + struct.pack("256i", *(maximum + minimum + [0] * 64 + flat)))
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except BaseException:
            os.close(self.fd)
            self.closed = True
            raise

    def _event(self, kind: int, code: int, value: int) -> None:
        """Write one raw event to the uinput descriptor."""
        os.write(self.fd, self.EVENT.pack(0, 0, kind, code, value))

    def write(self, buttons: set[str], axes: dict[str, int]) -> None:
        """Publish only changed controls followed by one synchronization event."""
        changed = False
        normalized_axes = {name: int(axes.get(name, 0)) for name in AXIS_CODES}
        for name, code in BUTTON_CODES.items():
            before, after = name in self.buttons, name in buttons
            if before != after:
                self._event(EV_KEY, code, int(after))
                changed = True
        for name, code in AXIS_CODES.items():
            value = normalized_axes[name]
            if self.axes[name] != value:
                self._event(EV_ABS, code, value)
                changed = True
        self.buttons, self.axes = set(buttons), normalized_axes
        if changed:
            self._event(EV_SYN, SYN_REPORT, 0)

    def close(self) -> None:
        """Neutralize and remove the kernel virtual controller."""
        if self.closed:
            return
        self.write(set(), {name: 0 for name in AXIS_CODES})
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)
        self.closed = True


def retroarch_running(proc_root: Path = Path("/proc")) -> bool:
    """Return whether a RetroArch process is currently present."""
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        if _text(entry / "comm").casefold().startswith("retroarch"):
            return True
    return False


def merged_joypad_index(sys_root: Path = Path("/sys/class/input")) -> int | None:
    """Return the current Linux joystick index for the merged device."""
    for item in sorted(sys_root.glob("js*"), key=lambda path: int(path.name[2:])):
        if _text(item / "device/name") == DEVICE_NAME:
            return int(item.name[2:])
    return None


class MergedGamepadDevice:
    """Persistent daemon owning the merged device and physical-controller source."""

    EVENT = struct.Struct("llHHi")

    def __init__(self, controller_config: Path, retroarch_config: Path,
                 socket_path: Path | None = None,
                 sink=None, proc_root: Path = Path("/proc"),
                 sys_root: Path = Path("/sys/class/input"),
                 dev_root: Path = Path("/dev/input")) -> None:
        self.saved = load_controller(controller_config)
        self.retroarch_config = retroarch_config
        self.proc_root, self.sys_root, self.dev_root = proc_root, sys_root, dev_root
        self.state = MergeState()
        self.mapper = PhysicalMapper(self.saved["mapping"], self.state)
        self.sink = sink or UInputMergedGamepad()
        self.socket_path = socket_path
        self.socket = None
        self.descriptor = None
        self.virtual_updated_at = 0.0
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="virtualglove-player1", daemon=True)
        try:
            self._install_index()
            if socket_path is not None:
                socket_path.parent.mkdir(parents=True, exist_ok=True)
                if socket_path.is_symlink():
                    raise ValueError("refusing symbolic merged-gamepad socket")
                try:
                    socket_path.unlink()
                except FileNotFoundError:
                    pass
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                self.socket.bind(str(socket_path))
                os.chmod(str(socket_path), 0o660)
                self.socket.setblocking(False)
        except BaseException:
            if self.socket is not None:
                self.socket.close()
                try:
                    self.socket_path.unlink()
                except FileNotFoundError:
                    pass
            self.sink.close()
            raise
        self.thread.start()

    def _install_index(self) -> None:
        """Wait for uinput enumeration and atomically manage the NES assignment."""
        for _attempt in range(40):
            index = merged_joypad_index(self.sys_root)
            if index is not None:
                current = self.retroarch_config.read_text() if self.retroarch_config.exists() else ""
                global_config = self.retroarch_config.with_name("retroarchcustom.cfg")
                hotkeys = translated_hotkey_bindings(
                    global_config.read_text() if global_config.exists() else "",
                    self.saved["mapping"])
                updated = merge_retroarch_config(current, index, hotkeys)
                if updated != current:
                    self.retroarch_config.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.retroarch_config.with_name("." + self.retroarch_config.name + ".tmp")
                    temporary.write_text(updated)
                    os.replace(str(temporary), str(self.retroarch_config))
                return
            time.sleep(0.05)
        raise RuntimeError("merged gamepad did not appear in /sys/class/input")

    def _discover(self) -> dict | None:
        """Find the saved physical controller without relying on an event number."""
        return find_saved_controller(
            self.saved, input_devices(self.sys_root, self.dev_root))

    def _publish(self) -> None:
        """Publish the current safely merged state."""
        self.sink.write(*self.state.desired())

    def _run(self) -> None:
        """Monitor game activity, physical events, and VirtualGlove datagrams."""
        while not self.stop.is_set():
            with self.lock:
                active = retroarch_running(self.proc_root)
                if active != self.state.active:
                    self.state.active = active
                    self._publish()
                if (self.state.virtual and self.virtual_updated_at and
                        time.monotonic() - self.virtual_updated_at >= VIRTUAL_TIMEOUT_SECONDS):
                    self.state.virtual = {}
                    self.virtual_updated_at = 0.0
                    self._publish()
            if self.descriptor is None:
                candidate = self._discover()
                if candidate:
                    joystick_descriptor = None
                    try:
                        joystick_descriptor = os.open(
                            candidate["joystick"], os.O_RDONLY | os.O_NONBLOCK)
                        mapping = translate_es_mapping(
                            self.saved["mapping"], joystick_descriptor)
                        self.descriptor = os.open(
                            candidate["event"], os.O_RDONLY | os.O_NONBLOCK)
                        self.mapper = PhysicalMapper(mapping, self.state)
                        self.mapper.axis_ranges = input_axis_ranges(
                            self.descriptor, mapping)
                    except (OSError, ValueError):
                        self.descriptor = None
                    finally:
                        if joystick_descriptor is not None:
                            os.close(joystick_descriptor)
            try:
                sources = [] if self.descriptor is None else [self.descriptor]
                if self.socket is not None:
                    sources.append(self.socket)
                if not sources:
                    self.stop.wait(0.25)
                    continue
                ready, _, _ = select.select(sources, [], [], 0.1)
                if not ready:
                    continue
                with self.lock:
                    if self.socket is not None and self.socket in ready:
                        try:
                            payload = self.socket.recv(8193)
                            incoming = (virtual_state(json.loads(payload))
                                        if len(payload) <= 8192 else None)
                            if incoming is not None:
                                self.state.virtual = incoming
                                self.virtual_updated_at = time.monotonic()
                        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
                            pass
                    if self.descriptor is not None and self.descriptor in ready:
                        payload = os.read(self.descriptor, self.EVENT.size * 64)
                        if not payload:
                            raise OSError("physical Player 1 disconnected")
                        for offset in range(0, len(payload) - self.EVENT.size + 1, self.EVENT.size):
                            _sec, _usec, kind, code, value = self.EVENT.unpack_from(payload, offset)
                            if kind in (EV_KEY, EV_ABS):
                                self.mapper.event(kind, code, value)
                    self._publish()
            except OSError:
                if self.descriptor is not None:
                    try:
                        os.close(self.descriptor)
                    except OSError:
                        pass
                    self.descriptor = None
                with self.lock:
                    self.state.release_physical()
                    self._publish()

    def write_state(self, state: dict) -> None:
        """Apply a validated VirtualGlove state directly for tests or embedding."""
        state = virtual_state(state)
        if state is None:
            raise ValueError("invalid merged-gamepad state")
        with self.lock:
            self.state.virtual = state
            self.virtual_updated_at = time.monotonic()
            self._publish()

    def release(self) -> None:
        """Release only the VirtualGlove source."""
        with self.lock:
            self.state.virtual = {}
            self.virtual_updated_at = 0.0
            self._publish()

    def close(self) -> None:
        """Stop monitoring and release every owned resource."""
        self.stop.set()
        self.thread.join(timeout=2)
        if self.descriptor is not None:
            os.close(self.descriptor)
        if self.socket is not None:
            self.socket.close()
            try:
                self.socket_path.unlink()
            except FileNotFoundError:
                pass
        self.sink.close()


class MergedGamepadClient:
    """Receiver-side publisher for the persistent merged-gamepad daemon."""

    def __init__(self, socket_path: Path) -> None:
        self.path = socket_path
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.closed = False

    def write_state(self, state: dict) -> None:
        """Send one bounded state to the persistent merger."""
        if self.closed:
            raise RuntimeError("merged-gamepad client is closed")
        payload = merged_payload(state)
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        if len(encoded) > 8192:
            raise ValueError("merged-gamepad state is too large")
        try:
            self.socket.sendto(encoded, str(self.path))
        except (FileNotFoundError, ConnectionRefusedError, BlockingIOError):
            # The persistent daemon may still be binding during a service
            # restart. The next authenticated state retries automatically.
            pass

    def release(self) -> None:
        """Send a neutral VirtualGlove state when the receiver times out."""
        if not self.closed:
            self.write_state({})

    def close(self) -> None:
        """Release VirtualGlove state and close the local socket."""
        if self.closed:
            return
        try:
            self.release()
        finally:
            self.socket.close()
            self.closed = True


def main() -> int:
    """Run the persistent merged-gamepad service."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve",))
    parser.add_argument("--controller-config", type=Path, required=True)
    parser.add_argument("--retroarch-config", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    args = parser.parse_args()
    device = MergedGamepadDevice(args.controller_config, args.retroarch_config,
                                 socket_path=args.socket)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0
    finally:
        device.close()


if __name__ == "__main__":
    raise SystemExit(main())
