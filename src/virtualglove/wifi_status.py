# Project: VirtualGlove
# File: src/virtualglove/wifi_status.py
# Purpose: Read fresh, non-secret host Wi-Fi health from the shared application data directory.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Read fresh physical-link broadcasts for authenticated console discovery.
#   2026-09-06 - Reject stale, missing, and malformed host connectivity telemetry.

"""A missing sampler is unknown, not evidence that Wi-Fi is disconnected."""
import json
import ipaddress
import math
import time
from pathlib import Path

STATUS_PATH = Path(__file__).resolve().parents[2] / 'data/wifi-status.json'


def _read_status(path, field):
    """Read at most 1 KiB and accept only telemetry sampled within fifteen seconds."""
    try:
        with path.open() as stream:
            value = json.loads(stream.read(1025))
        if not isinstance(value,dict) or value.get('version') not in (1,2):
            return 'unavailable'
        stamp = value.get('observed_at')
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0 <= time.time()-stamp <= 15:
            return 'unavailable'
        state = value.get(field)
        if field == 'networking' and field not in value:
            # Old samplers can confirm Wi-Fi, but cannot rule out Ethernet.
            return 'connected' if value.get('state') == 'connected' else 'unavailable'
        return state if state in ('connected','disconnected','unavailable') else 'unavailable'
    except (OSError,ValueError,TypeError,RecursionError):
        return 'unavailable'


def read_wifi_status(path=STATUS_PATH):
    """Read the backward-compatible wireless-only field."""
    return _read_status(path, 'state')


def read_network_status(path=STATUS_PATH):
    """Read aggregate physical Wi-Fi/Ethernet health; stale data is unknown."""
    return _read_status(path, 'networking')


def read_discovery_addresses(path=STATUS_PATH):
    """Return fresh, bounded host-LAN broadcasts for paired-console discovery."""
    try:
        with path.open() as stream:
            value = json.loads(stream.read(2049))
        if not isinstance(value, dict) or value.get('version') != 2:
            return ()
        stamp = value.get('observed_at')
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not 0 <= time.time() - stamp <= 15):
            return ()
        broadcasts = value.get('broadcasts')
        if not isinstance(broadcasts, list) or len(broadcasts) > 8:
            return ()
        result = []
        for raw in broadcasts:
            if not isinstance(raw, str):
                return ()
            address = ipaddress.IPv4Address(raw)
            if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
                return ()
            text = str(address)
            if text not in result:
                result.append(text)
        return tuple(result[:4])
    except (OSError, ValueError, TypeError, RecursionError):
        return ()
