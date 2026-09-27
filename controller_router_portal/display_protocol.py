"""Validated, app-neutral requests for the UNO Q's 13 by 8 Matrix."""
from __future__ import annotations

import json
from pathlib import Path

WIDTH = 13
HEIGHT = 8
PIXELS = WIDTH * HEIGHT
APPS = frozenset({"virtualglove", "rob_vision"})


def validate_manifest(document: object, app: str) -> dict:
    if not isinstance(document, dict) or document.get("schema") != 1 or document.get("app") != app:
        raise ValueError("Unsupported Matrix manifest")
    animations = document.get("animations")
    if not isinstance(animations, dict) or not animations or len(animations) > 64:
        raise ValueError("Matrix animations are missing or too numerous")
    for name, animation in animations.items():
        if not isinstance(name, str) or not name or len(name) > 48 or not name.replace("_", "").isalnum():
            raise ValueError("Invalid Matrix animation name")
        if not isinstance(animation, dict) or animation.get("loop") not in (True, False):
            raise ValueError("Invalid Matrix animation")
        frames = animation.get("frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 128:
            raise ValueError("Invalid Matrix frame count")
        for frame in frames:
            if not isinstance(frame, dict) or type(frame.get("ms")) is not int or not 50 <= frame["ms"] <= 5000:
                raise ValueError("Invalid Matrix frame duration")
            rows = frame.get("rows")
            if (not isinstance(rows, list) or len(rows) != HEIGHT or
                    any(not isinstance(row, str) or len(row) != WIDTH or
                        any(pixel not in "01234567" for pixel in row) for row in rows)):
                raise ValueError("A Matrix frame must have eight 13-pixel grayscale rows")
    return document


def load_manifest(path: Path, app: str) -> dict:
    if app not in APPS or path.is_symlink():
        raise ValueError("Untrusted Matrix manifest")
    if path.stat().st_size > 1_000_000:
        raise ValueError("Matrix manifest is too large")
    return validate_manifest(json.loads(path.read_text()), app)


def validate_request(message: object) -> dict:
    if not isinstance(message, dict) or message.get("version") != 1 or message.get("app") not in APPS:
        raise ValueError("Invalid Matrix request")
    if message.get("action") not in {"play", "clear", "pairing", "status"}:
        raise ValueError("Unknown Matrix action")
    if message["action"] == "play":
        name = message.get("animation")
        if not isinstance(name, str) or not name or len(name) > 48:
            raise ValueError("Invalid Matrix animation")
    if message["action"] == "pairing":
        pin = message.get("pin")
        identity = message.get("identity")
        if (not isinstance(pin, str) or len(pin) != 6 or not pin.isdigit() or
                not isinstance(identity, str) or len(identity) != 7 or
                any(letter not in "0123456789ABCDEF" for letter in identity)):
            raise ValueError("Invalid pairing display")
    if message["action"] == "status":
        label = message.get("text")
        if (not isinstance(label, str) or not 1 <= len(label) <= 3 or
                any(letter not in "0123456789ABCDEFINP" for letter in label)):
            raise ValueError("Invalid Matrix status text")
    return message
