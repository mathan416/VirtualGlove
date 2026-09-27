"""RetroArch udev joypad order, independent of Linux jsN numbering."""

from __future__ import annotations

import ctypes
import re
from pathlib import Path

def retroarch_udev_event_nodes() -> list[str]:
    """List joypad event nodes in RetroArch's udev discovery order.

    RetroArch's udev driver numbers event devices independently of Linux jsN.
    In particular, another virtual pad can make those two indices differ.
    """
    try:
        udev = ctypes.CDLL("libudev.so.1")
    except OSError as exc:
        raise RuntimeError("libudev is required to map RetroArch controllers.") from exc
    signatures = {
        "udev_new": (ctypes.c_void_p, []),
        "udev_unref": (ctypes.c_void_p, [ctypes.c_void_p]),
        "udev_enumerate_new": (ctypes.c_void_p, [ctypes.c_void_p]),
        "udev_enumerate_unref": (ctypes.c_void_p, [ctypes.c_void_p]),
        "udev_enumerate_add_match_property": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]),
        "udev_enumerate_add_match_subsystem": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p]),
        "udev_enumerate_scan_devices": (ctypes.c_int, [ctypes.c_void_p]),
        "udev_enumerate_get_list_entry": (ctypes.c_void_p, [ctypes.c_void_p]),
        "udev_list_entry_get_name": (ctypes.c_char_p, [ctypes.c_void_p]),
        "udev_list_entry_get_next": (ctypes.c_void_p, [ctypes.c_void_p]),
        "udev_device_new_from_syspath": (ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p]),
        "udev_device_get_devnode": (ctypes.c_char_p, [ctypes.c_void_p]),
        "udev_device_unref": (ctypes.c_void_p, [ctypes.c_void_p]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(udev, name)
        function.restype, function.argtypes = result, arguments
    context = udev.udev_new()
    if not context:
        raise RuntimeError("Could not initialize udev for RetroArch controller mapping.")
    enumeration = None
    try:
        enumeration = udev.udev_enumerate_new(context)
        if not enumeration:
            raise RuntimeError("Could not enumerate RetroArch controllers.")
        udev.udev_enumerate_add_match_property(enumeration, b"ID_INPUT_JOYSTICK", b"1")
        udev.udev_enumerate_add_match_subsystem(enumeration, b"input")
        if udev.udev_enumerate_scan_devices(enumeration) < 0:
            raise RuntimeError("Could not scan RetroArch controllers.")
        nodes = []
        item = udev.udev_enumerate_get_list_entry(enumeration)
        while item:
            path = udev.udev_list_entry_get_name(item)
            device = udev.udev_device_new_from_syspath(context, path)
            if device:
                try:
                    node = udev.udev_device_get_devnode(device)
                    if node and re.fullmatch(rb"/dev/input/event\d+", node):
                        nodes.append(node.decode())
                finally:
                    udev.udev_device_unref(device)
            item = udev.udev_list_entry_get_next(item)
        return nodes
    finally:
        if enumeration:
            udev.udev_enumerate_unref(enumeration)
        udev.udev_unref(context)


def retroarch_index_for_js(js_index: int, sys_root: Path = Path("/sys/class/input"),
                           event_nodes: list[str] | None = None) -> int:
    """Find the RetroArch udev slot for the same input device as jsN."""
    events = event_nodes if event_nodes is not None else retroarch_udev_event_nodes()
    joystick = sys_root / f"js{js_index}" / "device"
    for index, node in enumerate(events):
        event_device = sys_root / Path(node).name / "device"
        if event_device.exists() and joystick.samefile(event_device):
            return index
    raise RuntimeError("Merged pad was not found in RetroArch's udev controller list.")
