"""Local-only client for Controller Router's Matrix and input lease."""
from __future__ import annotations

import json
import socket
from pathlib import Path

SOCKET = Path("/run/user/1000/controller-router-portal/control.sock")


def request(message: dict, timeout: float = 2.0) -> dict:
    encoded = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > 1024:
        raise ValueError("Controller Router request is too large")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(SOCKET))
        connection.sendall(encoded)
        with connection.makefile("rb") as stream:
            response = stream.readline(4096)
    result = json.loads(response)
    if not isinstance(result, dict):
        raise ValueError("Invalid Controller Router response")
    return result


def display(app: str, action: str, **details) -> bool:
    result = request({"action": "display", "request": {"version": 1, "app": app,
                      "action": action, **details}})
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result.get("accepted") is True


def lease(app: str) -> bool:
    return request({"action": "lease", "app": app}).get("active") is True
