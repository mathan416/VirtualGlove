# Project: VirtualGlove
# File: src/virtualglove/kiyo_camera.py
# Purpose: Apply opt-in volatile Kiyo Pro controls through the Linux camera interface.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Separated device identity checks from control-descriptor opening.
#   2026-09-06 - Add identity-checked HDR-off and automatic fixed-rate exposure.
# Full history: docs/CHANGELOG.md and Git history.

"""Apply the measured Kiyo capture candidate without onboard SAVE commands.

HDR protocol reference: https://github.com/soyersoyer/kiyoproctrls
Other camera models are left untouched. Camera settings are not player data.
"""

import ctypes
import os
from pathlib import Path
import struct
import sys

GUID = bytes.fromhex('d09ee4237811314fae52d2fb8a8d3b48')
HDR_OFF = bytes.fromhex('ff02000000000000')
AUTO_EXPOSURE = 0x009a0901
DYNAMIC_FRAMERATE = 0x009a0903


class ExtensionQuery(ctypes.Structure):
    """Represent the architecture-sized Linux UVC extension control query."""
    _fields_ = [('unit', ctypes.c_uint8), ('selector', ctypes.c_uint8),
                ('query', ctypes.c_uint8), ('size', ctypes.c_uint16), ('data', ctypes.c_void_p)]


def extension_unit(descriptors):
    """Parse bounded USB descriptors and locate the matching extension GUID."""
    offset = 0
    while offset + 2 <= len(descriptors):
        length = descriptors[offset]
        if length < 2 or offset + length > len(descriptors):
            raise ValueError('Malformed camera USB descriptor')
        block = descriptors[offset:offset + length]
        if len(block) >= 20 and block[1:3] == b'\x24\x06' and block[4:20] == GUID:
            return block[3]
        offset += length
    raise ValueError('Kiyo Pro HDR extension not found')


def apply_controls(fd, unit, ioctl):
    """Set only HDR-off and automatic fixed-rate exposure; never save onboard."""
    request = (3 << 30) | (ctypes.sizeof(ExtensionQuery) << 16) | (ord('u') << 8) | 0x21
    length = ctypes.c_uint16()
    ioctl(fd, request, ExtensionQuery(unit, 1, 0x85, 2, ctypes.addressof(length)))
    if not 8 <= length.value <= 64:
        raise ValueError('Unexpected Kiyo Pro HDR control size')
    payload = ctypes.create_string_buffer(length.value)
    payload[0:8] = HDR_OFF
    ioctl(fd, request, ExtensionQuery(unit, 1, 0x01, length.value, ctypes.addressof(payload)))
    for control, value in ((AUTO_EXPOSURE, 3), (DYNAMIC_FRAMERATE, 0)):
        ioctl(fd, 0xc008561c, bytearray(struct.pack('Ii', control, value)))
    # Verify the standard controls. The vendor command has no proven HDR readback.
    for control, expected in ((AUTO_EXPOSURE, 3), (DYNAMIC_FRAMERATE, 0)):
        data = bytearray(struct.pack('Ii', control, 0))
        ioctl(fd, 0xc008561b, data)
        if struct.unpack('Ii', data)[1] != expected:
            raise RuntimeError('Camera exposure setting did not take effect')


def kiyo_extension_unit(device, sysfs=Path('/sys/class/video4linux')):
    """Return the Kiyo extension unit after a read-only physical identity check."""
    if sys.platform != 'linux':
        return None
    name = 'video' + str(device) if str(device).isdigit() else Path(device).resolve().name
    if not name.startswith('video') or not name[5:].isdigit():
        return None
    path = (sysfs / name).resolve()
    usb = next((p for p in path.parents if (p / 'idVendor').is_file()), None)
    if (usb is None or (usb / 'idVendor').read_text().strip() != '1532'
            or (usb / 'idProduct').read_text().strip() != '0e05'):
        return None
    return extension_unit((usb / 'descriptors').read_bytes())


def configure_kiyo(device, sysfs=Path('/sys/class/video4linux')):
    """Check physical USB identity before opening a device for control writes."""
    unit = kiyo_extension_unit(device, sysfs)
    if unit is None:
        return False
    from fcntl import ioctl
    name = 'video' + str(device) if str(device).isdigit() else Path(device).resolve().name
    fd = os.open('/dev/' + name, os.O_RDWR)
    try:
        apply_controls(fd, unit, ioctl)
    finally:
        os.close(fd)
    return True
