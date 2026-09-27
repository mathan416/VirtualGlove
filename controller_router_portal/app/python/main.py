"""Private App Lab endpoint for the Controller Router Matrix sketch."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from arduino.app_utils import Bridge

TOKEN = Path("/app/data/matrix-token").read_text().strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        try:
            ready = Bridge.call("get_router_firmware") == "controller-router-0.2.0"
        except Exception:
            ready = False
        body = json.dumps({"ready": ready}).encode()
        self.send_response(200 if ready else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/frame" or self.headers.get("X-Router-Token") != TOKEN:
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 256:
                raise ValueError("Invalid frame size")
            rows = json.loads(self.rfile.read(size))["rows"]
            if (not isinstance(rows, list) or len(rows) != 8 or
                    any(not isinstance(row, str) or len(row) != 13 or
                        any(pixel not in "01234567" for pixel in row) for row in rows)):
                raise ValueError("Invalid frame")
            delivered = Bridge.call("draw_router_frame", "".join(rows)) is True
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(400)
            return
        except Exception:
            self.send_error(503)
            return
        body = json.dumps({"delivered": delivered}).encode()
        self.send_response(200 if delivered else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8123), Handler).serve_forever()
