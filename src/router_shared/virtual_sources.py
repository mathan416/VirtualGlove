"""Validate optional maker-controller mappings supplied by a host project."""

from __future__ import annotations

import json
import os
from pathlib import Path


def configured_sources(path: Path | None = None) -> list[dict]:
    """Return bounded virtual-source descriptors; the core knows no project names."""
    selected = path or os.environ.get("CONTROLLER_ROUTER_SOURCES_FILE")
    if not selected:
        return []
    raw = Path(selected).read_bytes()
    if len(raw) > 65536:
        raise ValueError("Controller Router source file is too large.")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ValueError("Unsupported Controller Router source file.")
    sources = document.get("sources")
    if not isinstance(sources, list) or len(sources) > 16:
        raise ValueError("Invalid Controller Router source list.")
    result = []
    identities = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"name", "vendor", "product", "mapping"}:
            raise ValueError("Invalid virtual controller descriptor.")
        name, vendor, product = (source[key] for key in ("name", "vendor", "product"))
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            raise ValueError("Invalid virtual controller name.")
        if not all(isinstance(value, str) and len(value) == 4 and
                   all(char in "0123456789abcdefABCDEF" for char in value)
                   for value in (vendor, product)):
            raise ValueError("Invalid virtual controller vendor or product.")
        mapping = source["mapping"]
        if not isinstance(mapping, list) or not 1 <= len(mapping) <= 64:
            raise ValueError("Invalid virtual controller mapping.")
        for entry in mapping:
            if (not isinstance(entry, dict) or
                    set(entry) != {"name", "type", "code", "value", "evdev_code"} or
                    not isinstance(entry["name"], str) or
                    entry["type"] not in ("button", "axis", "hat") or
                    any(isinstance(entry[key], bool) or not isinstance(entry[key], int)
                        for key in ("code", "value", "evdev_code")) or
                    not all(0 <= entry[key] <= 0xFFFF for key in ("code", "evdev_code")) or
                    not -0x8000 <= entry["value"] <= 0x7FFF):
                raise ValueError("Invalid virtual controller button mapping.")
        identity = (name, vendor.lower(), product.lower())
        if identity in identities:
            raise ValueError("Duplicate virtual controller descriptor.")
        identities.add(identity)
        result.append({"name": name, "vendor": vendor.lower(),
                       "product": product.lower(), "mapping": mapping})
    return result
