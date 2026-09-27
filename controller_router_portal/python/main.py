"""Port-80 App Lab entry page for the active UNO Q controller."""
from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ASSETS = Path(__file__).with_name("assets")
PAGE = Path(__file__).with_name("index.html")


def broker(message: dict) -> dict:
    connection = HTTPConnection("portal-host-bridge", 8122, timeout=10)
    try:
        connection.request("POST", "/request", json.dumps(message), {"Content-Type": "application/json"})
        response = connection.getresponse()
        return json.load(response)
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def app_origin(self):
        origin = self.headers.get("Origin", "")
        try:
            source = urlsplit(origin)
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            return (source.scheme == "http" and source.hostname == host and
                    source.port in (8100, 8101))
        except ValueError:
            return False

    def do_OPTIONS(self):
        if urlsplit(self.path).path != "/api/select" or not self.app_origin():
            self.send_error(403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def send_json(self, code: int, value: dict) -> None:
        body = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if self.app_origin():
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/state":
            try:
                self.send_json(200, broker({"action": "state"}))
            except (OSError, ValueError):
                self.send_json(503, {"error": "The UNO Q launcher is unavailable."})
        elif path == "/" or path in ("/assets/pixel-pal.png", "/assets/buddy.png"):
            asset = PAGE if path == "/" else ASSETS / path.rsplit("/", 1)[-1]
            body = asset.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if path == "/" else "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/select":
            self.send_error(404)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.send_json(415, {"error": "JSON required."})
            return
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "same-site", "none"):
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        origin = self.headers.get("Origin")
        if origin and not self.app_origin() and (urlsplit(origin).scheme != "http" or
                       urlsplit(origin).netloc.lower() != self.headers.get("Host", "").lower()):
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 128:
                raise ValueError("Invalid request size.")
            app = json.loads(self.rfile.read(size)).get("app")
            self.send_json(202, broker({"action": "select", "app": app}))
        except (OSError, ValueError, AttributeError, TypeError):
            self.send_json(400, {"error": "Invalid controller choice."})

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
