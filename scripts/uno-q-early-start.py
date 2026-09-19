#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/uno-q-early-start.py
# Purpose: Release the installed sketch without resetting or flashing it.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Read the release's precompiled Matrix image.
#   2026-09-04 - Added an explicit, image-verified early-start experiment.
# Full history: docs/CHANGELOG.md and Git history.

"""Release the UNO Q sketch early; read-only unless --release is supplied."""

import argparse
from pathlib import Path
import subprocess
import tempfile
import time

APP = Path('/home/arduino/ArduinoApps/virtualglove')
OPENOCD = '/opt/openocd/bin/openocd'


def configuration(directory: Path, image: bytes, release: bool) -> str:
    """Attach only to the memory access port; never configure reset pins or halt."""
    checks = []
    for index, offset in enumerate((0, 256, len(image) // 2, len(image) - 64)):
        (directory / ("expected%d.bin" % index)).write_bytes(image[offset:offset + 64])
        checks.append('dump_image {%s/actual.bin} %d 64\nif {[contents {%s/actual.bin}] ne [contents {%s/expected%d.bin}]} {error "Sketch sample mismatch; refusing release"}' % (directory, 0x08100000 + offset, directory, directory, index))
    return '''
adapter driver linuxgpiod
adapter gpio swclk 26 -chip 1
adapter gpio swdio 25 -chip 1
transport select swd
source [find target/swj-dp.tcl]
swj_newdap pg cpu -irlen 4 -expected-id 0x0be12477
dap create pg.dap -chain-position pg.cpu
target create pg.mem mem_ap -dap pg.dap -ap-num 0
reset_config none
gdb port disabled
tcl port disabled
telnet port disabled
init
proc contents {path} {
    set f [open $path rb]
    set data [read $f]
    close $f
    return $data
}
%s
echo "VirtualGlove sketch header and code samples verified"
set flag [lindex [read_memory 0x40036400 32 1] 0]
if {$flag == 0xcaffeeee} {
    echo "ALREADY_RELEASED: no write"
} elseif {$flag != 0} {
    error "Unexpected startup flag; refusing release"
} elseif {%d} {
    mww 0x40036400 0xcaffeeee
    if {[lindex [read_memory 0x40036400 32 1] 0] != 0xcaffeeee} {
        error "Release readback failed"
    }
    echo "RELEASED: no reset, halt, or flash"
} else {
    echo "WAITING: check only; no write"
}
shutdown
''' % ('\n'.join(checks), int(release))


def main() -> None:
    """Require this board and startup app, and compare flashed header and code samples."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true',
                        help='Release a waiting sketch after header and code-sample verification.')
    parser.add_argument('--wait-router', action='store_true',
                        help='Wait up to 30 seconds for the router during startup.')
    args = parser.parse_args()
    board = Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    if b'arduino,imola' not in board:
        raise SystemExit('Only the verified UNO Q board is supported.')
    if Path('/var/lib/arduino-app-cli/default.app').read_text().strip() != str(APP):
        raise SystemExit('VirtualGlove is not the startup app; refusing.')
    deadline = time.monotonic() + (30 if args.wait_router else 0)
    while subprocess.run(['systemctl', 'is-active', '--quiet', 'arduino-router.service']).returncode:
        if time.monotonic() >= deadline:
            raise SystemExit('Router is unavailable; leaving normal startup in control.')
        time.sleep(0.25)
    candidates = (
        APP / 'firmware/matrix/virtualglove-matrix.elf-zsk.bin',
        APP / '.cache/sketch/sketch.ino.elf-zsk.bin',
    )
    image_path = next((path for path in candidates if path.is_file()), None)
    if image_path is None:
        raise SystemExit('Installed sketch image is unavailable; leaving normal startup in control.')
    image = image_path.read_bytes()
    if (len(image) < 16 or len(image) > 786432 or image[:4] != b'\x7fELF'
            or image[7] != 1 or image[12:14] != b'A#'
            or not image[14] & 8 or image[14] & 4):
        raise SystemExit('Expected a valid Wait for App sketch image; refusing.')
    with tempfile.TemporaryDirectory(prefix='pg-early-start-') as temp:
        directory = Path(temp)
        config = directory / 'check.cfg'
        config.write_text(configuration(directory, image, args.release))
        try:
            subprocess.run([OPENOCD, '-s', '/opt/openocd/share/openocd/scripts',
                            '-f', str(config)], check=True, timeout=20)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            # The router or another boot component may already own the SWD GPIO
            # lines. Early release is only an optimization; normal startup remains
            # authoritative and must not leave a failed user unit behind.
            print("VirtualGlove early-start unavailable; leaving normal startup in control: "
                  + str(error))


if __name__ == '__main__':
    main()
