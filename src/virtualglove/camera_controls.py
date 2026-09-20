# Project: VirtualGlove
# File: src/virtualglove/camera_controls.py
# Purpose: Apply capability-checked, volatile standard V4L2 latency controls.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Promote capability-reported manual exposure and gain to runtime use.
#   2026-09-08 - Added active-stream manual exposure helpers for isolated testing.
#   2026-09-07 - Added portable low-latency exposure negotiation.
# Full history: docs/CHANGELOG.md and Git history.

"""Apply only standard camera controls that a Linux V4L2 device advertises."""

from __future__ import annotations

import os
import struct
import sys
from typing import Callable


VIDIOC_QUERYCTRL = 0xC0445624
VIDIOC_G_CTRL = 0xC008561B
VIDIOC_S_CTRL = 0xC008561C
V4L2_CTRL_FLAG_DISABLED = 0x0001
EXPOSURE_AUTO = 0x009A0901
EXPOSURE_ABSOLUTE = 0x009A0902
EXPOSURE_AUTO_PRIORITY = 0x009A0903
GAIN = 0x00980913


def _query(fd: int, control: int, ioctl: Callable) -> dict | None:
    """Return one enabled standard control description, or None if unsupported."""
    data = bytearray(68)
    struct.pack_into("I", data, 0, control)
    try:
        ioctl(fd, VIDIOC_QUERYCTRL, data)
    except OSError:
        return None
    identifier, kind = struct.unpack_from("II", data, 0)
    minimum, maximum, step, default = struct.unpack_from("iiii", data, 40)
    flags = struct.unpack_from("I", data, 56)[0]
    if identifier != control or flags & V4L2_CTRL_FLAG_DISABLED:
        return None
    name = bytes(data[8:40]).split(b"\0", 1)[0].decode("ascii", "replace")
    return {
        "id": identifier, "type": kind, "name": name,
        "minimum": minimum, "maximum": maximum, "step": step,
        "default": default,
    }


def _set_verified(fd: int, control: dict, value: int, ioctl: Callable) -> bool:
    """Set and read back one already-queried control without guessing its range."""
    if not control["minimum"] <= value <= control["maximum"]:
        return False
    step = max(1, int(control["step"]))
    if (value - int(control["minimum"])) % step:
        return False
    ioctl(fd, VIDIOC_S_CTRL, bytearray(struct.pack("Ii", control["id"], value)))
    data = bytearray(struct.pack("Ii", control["id"], 0))
    ioctl(fd, VIDIOC_G_CTRL, data)
    return struct.unpack("Ii", data)[1] == value


def configure_low_latency(device: str, ioctl: Callable | None = None) -> dict:
    """Disable variable frame-rate exposure when the camera supports that control.

    Exposure itself remains automatic. Unsupported controls are reported and never
    written, which keeps this safe for ordinary UVC cameras.
    """
    report = {
        "requested": "low_latency", "supported": False, "applied": False,
        "auto_exposure": False, "fixed_frame_rate": False,
    }
    if not sys.platform.startswith("linux"):
        report["reason"] = "standard V4L2 controls require Linux"
        return report
    if ioctl is None:
        from fcntl import ioctl as system_ioctl
        ioctl = system_ioctl
    fd = os.open(str(device), os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
    try:
        automatic = _query(fd, EXPOSURE_AUTO, ioctl)
        priority = _query(fd, EXPOSURE_AUTO_PRIORITY, ioctl)
        report["supported"] = bool(automatic or priority)
        # V4L2 value 3 is aperture-priority automatic exposure. Only request it
        # when the device explicitly reports that value inside its legal range.
        if automatic:
            report["auto_exposure"] = _set_verified(fd, automatic, 3, ioctl)
        if priority:
            report["fixed_frame_rate"] = _set_verified(fd, priority, 0, ioctl)
        report["applied"] = bool(report["fixed_frame_rate"])
        if not report["supported"]:
            report["reason"] = "camera exposes no standard latency controls"
        elif not report["applied"]:
            report["reason"] = "camera did not accept fixed-frame-rate exposure"
        return report
    finally:
        os.close(fd)


def configure_manual_on_fd(
    fd: int, exposure: int, gain: int, ioctl: Callable | None = None,
) -> dict:
    """Apply capability-checked manual settings to an already-streaming fd.

    This helper intentionally does not open the camera. A second descriptor can
    disrupt an active UVC stream on otherwise standards-compliant cameras.
    """
    if ioctl is None:
        from fcntl import ioctl as system_ioctl
        ioctl = system_ioctl
    controls = {
        "automatic": _query(fd, EXPOSURE_AUTO, ioctl),
        "priority": _query(fd, EXPOSURE_AUTO_PRIORITY, ioctl),
        "exposure": _query(fd, EXPOSURE_ABSOLUTE, ioctl),
        "gain": _query(fd, GAIN, ioctl),
    }
    limits = {
        name: {
            key: int(control[key])
            for key in ("minimum", "maximum", "step", "default")
        }
        for name, control in (("exposure", controls["exposure"]),
                              ("gain", controls["gain"]))
        if control is not None
    }
    report = {
        "requested": "manual", "supported": all(controls.values()),
        "applied": False, "exposure": int(exposure), "gain": int(gain),
        "limits": limits,
    }
    if not report["supported"]:
        report["reason"] = "camera exposes an incomplete manual-control set"
        return report
    try:
        writes = (
            (controls["priority"], 0),
            (controls["automatic"], 1),
            (controls["exposure"], int(exposure)),
            (controls["gain"], int(gain)),
        )
        report["applied"] = all(
            _set_verified(fd, control, value, ioctl) for control, value in writes
        )
    except OSError as exc:
        report["reason"] = str(exc)
    if not report["applied"] and "reason" not in report:
        report["reason"] = "camera rejected one or more manual settings"
    return report


def restore_automatic_on_fd(fd: int, ioctl: Callable | None = None) -> bool:
    """Restore automatic, fixed-rate exposure through an owned stream fd."""
    if ioctl is None:
        from fcntl import ioctl as system_ioctl
        ioctl = system_ioctl
    automatic = _query(fd, EXPOSURE_AUTO, ioctl)
    priority = _query(fd, EXPOSURE_AUTO_PRIORITY, ioctl)
    if not automatic or not priority:
        return False
    try:
        return (
            _set_verified(fd, automatic, 3, ioctl)
            and _set_verified(fd, priority, 0, ioctl)
        )
    except OSError:
        return False
