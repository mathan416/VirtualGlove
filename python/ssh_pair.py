#!/usr/bin/env python3
# Project: VirtualGlove
# File: python/ssh_pair.py
# Purpose: Pair an UNO Q with a supported console over SSH without exposing credentials on the command line.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Password-authenticated console pairing using a temporary Python SSH client."""

from __future__ import annotations

import json
import os
import posixpath
import secrets
import shlex
import sys
from pathlib import Path

import paramiko
import socket

from powerglove_vision.resolver import resolve_ipv4


REMOTE_PROGRAM = """\
import grp
import os
import subprocess
import sys

source = sys.argv[1]
recalbox = os.path.isfile("/recalbox/recalbox.version")
batocera = os.path.isfile("/usr/share/batocera/batocera.version")
platform = "recalbox" if recalbox else ("batocera" if batocera else "retropie")
expected_platform = sys.argv[2]
destination = ("/recalbox/share/system/virtualglove/data/token" if recalbox else
               ("/userdata/system/virtualglove/data/token" if batocera else
                "/etc/virtualglove/token"))
try:
    if expected_platform != platform:
        raise ValueError("selected platform does not match this console (detected " + platform + ")")
    with open(source, encoding="utf-8") as token_file:
        token = token_file.readline().strip()
    assert 16 <= len(token) <= 256 and not any(character.isspace() for character in token)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = destination + ".pairing-tmp"
    with open(temporary, "w", encoding="utf-8") as token_file:
        token_file.write(token + "\\n")
    if not recalbox and not batocera:
        os.chmod(temporary, 0o640)
        os.chown(temporary, 0, grp.getgrnam("input").gr_gid)
    os.replace(temporary, destination)
    if recalbox:
        subprocess.check_call([
            "sh", "/recalbox/share/system/virtualglove/recalbox/virtualglove-service",
            "restart-receiver",
        ])
    elif batocera:
        subprocess.check_call([
            "/userdata/system/services/VirtualGlove", "restart-receiver",
        ])
    else:
        subprocess.check_call(["systemctl", "restart", "virtualglove-receiver.service"])
finally:
    try:
        os.unlink(source)
    except FileNotFoundError:
        pass
"""


def main() -> int:
    """Read one pairing request from standard input, install its token remotely, and report JSON status."""
    request = json.load(sys.stdin)
    known_hosts = Path(str(request["known_hosts"]))
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.touch(mode=0o600, exist_ok=True)
    os.chmod(known_hosts, 0o600)

    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None
    remote_token = None
    try:
        timeout = float(request.get("timeout", 30.0))
        client.connect(
            hostname=str(request["host"]),
            sock=socket.create_connection((resolve_ipv4(str(request["host"])), 22), timeout=timeout),
            username=str(request["username"]),
            password=str(request["password"]),
            timeout=timeout,
            auth_timeout=timeout,
            banner_timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        sftp = client.open_sftp()
        remote_token = posixpath.join(
            sftp.normalize("."), ".virtualglove-pairing-" + secrets.token_hex(16)
        )
        with sftp.file(remote_token, "wx") as token_file:
            token_file.write(str(request["token"]) + "\n")
        sftp.chmod(remote_token, 0o600)
        python_command = ("/usr/bin/python3 -c " + shlex.quote(REMOTE_PROGRAM) + " "
                          + shlex.quote(remote_token) + " "
                          + shlex.quote(str(request["platform"])))
        command = (python_command if str(request["username"]) == "root" else
                   "sudo -k -S -p '' " + python_command)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        if str(request["username"]) != "root":
            stdin.write(str(request["password"]) + "\n")
        stdin.flush()
        stdin.channel.shutdown_write()
        status = stdout.channel.recv_exit_status()
        error = stderr.read().decode("utf-8", "replace").strip()
        if status:
            raise RuntimeError(error.splitlines()[-1] if error else "Console pairing command failed")
        client.save_host_keys(str(known_hosts))
        os.chmod(known_hosts, 0o600)
        return 0
    finally:
        if sftp is not None and remote_token is not None:
            try:
                sftp.remove(remote_token)
            except OSError:
                pass
            sftp.close()
        client.close()
        request["password"] = ""
        request["token"] = ""


if __name__ == "__main__":
    raise SystemExit(main())
