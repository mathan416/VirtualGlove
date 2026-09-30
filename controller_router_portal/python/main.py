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
    connection = HTTPConnection("portal-host-bridge", 8122, timeout=22)
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
        elif path in ('/api/pairing-certificate', '/controller-router.crt', '/controller-router.mobileconfig'):
            try:
                public = broker({'action': 'pairing-certificate'})
                if 'certificate' not in public or 'fingerprint' not in public:
                    raise ValueError('Certificate not ready')
            except (OSError, ValueError):
                self.send_error(503, 'Secure Setup is starting. Try again shortly.')
                return
            if path == '/api/pairing-certificate':
                self.send_json(200, {'fingerprint': public['fingerprint']})
            elif path == '/controller-router.mobileconfig':
                import ssl, uuid, plistlib
                identity = str(uuid.uuid5(uuid.NAMESPACE_URL, public['fingerprint']))
                payload = {'PayloadType': 'com.apple.security.root', 'PayloadVersion': 1,
                    'PayloadIdentifier': 'org.controller-router.certificate.' + identity,
                    'PayloadUUID': str(uuid.uuid5(uuid.NAMESPACE_URL, identity + '.certificate')),
                    'PayloadDisplayName': 'Controller Router Secure Setup',
                    'PayloadContent': ssl.PEM_cert_to_DER_cert(public['certificate'])}
                body = plistlib.dumps({'PayloadType': 'Configuration', 'PayloadVersion': 1,
                    'PayloadIdentifier': 'org.controller-router.setup.' + identity,
                    'PayloadUUID': identity, 'PayloadDisplayName': 'Controller Router Secure Setup',
                    'PayloadDescription': 'Trust the local certificate for this UNO Q’s secure pairing page.',
                    'PayloadContent': [payload]}, fmt=plistlib.FMT_XML)
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-apple-aspen-config')
                self.send_header('Content-Disposition', 'attachment; filename="Controller-Router.mobileconfig"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = public['certificate'].encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-x509-ca-cert')
                self.send_header('Content-Disposition', 'attachment; filename="Controller-Router.crt"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        elif path.startswith('/guides/Controller-Router-') and path.endswith('.pdf') and path.count('/') == 2:
            try:
                body = PAGE.parent.joinpath('guides', path.rsplit('/', 1)[-1]).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path in ("/", "/setup", "/setup.html", "/pair", "/pair.html", "/help", "/help.html") or path in ("/assets/pixel-pal.png", "/assets/buddy.png"):
            pages = {"/": PAGE, "/setup": PAGE.with_name("setup.html"),
                     "/setup.html": PAGE.with_name("setup.html"),
                     "/pair": PAGE.with_name("trust.html"), "/pair.html": PAGE.with_name("trust.html"),
                     "/help": PAGE.with_name("help.html"), "/help.html": PAGE.with_name("help.html")}
            asset = pages.get(path, ASSETS / path.rsplit("/", 1)[-1])
            try:
                body = asset.read_bytes()
            except OSError:
                self.send_error(503, "Launcher asset unavailable; rerun the installer.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if path in pages else "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlsplit(self.path).path not in ("/api/select", "/api/routing"):
            self.send_error(404)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.send_json(415, {"error": "JSON required."})
            return
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "same-site", "none"):
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        origin = self.headers.get("Origin")
        try:
            allowed = not origin or self.app_origin() or (urlsplit(origin).scheme == "http" and
                       urlsplit(origin).netloc.lower() == self.headers.get("Host", "").lower())
        except ValueError:
            allowed = False
        if not allowed:
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= (32768 if urlsplit(self.path).path == "/api/routing" else 128):
                raise ValueError("Invalid request size.")
            incoming = json.loads(self.rfile.read(size))
            if urlsplit(self.path).path == "/api/routing":
                if not isinstance(incoming, dict):
                    raise ValueError("Invalid routing request.")
                incoming["action"] = "routing"
                result = broker(incoming)
                self.send_json(400 if result.get("error") else 200, result)
                return
            app = incoming.get("app")
            self.send_json(202, broker({"action": "select", "app": app}))
        except (OSError, ValueError, AttributeError, TypeError):
            self.send_json(400, {"error": "Invalid controller choice."})

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
