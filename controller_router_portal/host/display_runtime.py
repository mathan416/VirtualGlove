"""Play validated product animations through Controller Router's sole Matrix app."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from ..display_protocol import load_manifest, validate_request
except ImportError:  # Executed from the installed host script.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from display_protocol import load_manifest, validate_request

APP_ROOT = Path("/home/arduino/ArduinoApps")
MANIFESTS = {
    "virtualglove": APP_ROOT / "virtualglove/matrix/manifest.json",
    "rob_vision": APP_ROOT / "rob-vision/matrix/manifest.json",
}
TOKEN = APP_ROOT / "controller-router/data/matrix-token"

GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "I": ("111", "010", "010", "010", "111"),
    "N": ("101", "111", "111", "111", "101"),
    "P": ("110", "101", "110", "100", "100"),
}


def code_frame(code: str) -> list[str]:
    """Show at most three PIN or certificate characters at once."""
    if not 1 <= len(code) <= 3 or any(letter not in GLYPHS for letter in code):
        raise ValueError("Invalid Matrix code")
    pixels = [["0"] * 13 for _ in range(8)]
    left = (13 - (len(code) * 4 - 1)) // 2
    for offset, letter in enumerate(code):
        for y, row in enumerate(GLYPHS[letter]):
            for x, pixel in enumerate(row):
                if pixel == "1":
                    pixels[y + 1][left + offset * 4 + x] = "7"
    return ["".join(row) for row in pixels]


class MatrixScheduler:
    def __init__(self, send=None, clock=time.monotonic):
        self.send = send or self._send
        self.clock = clock
        self.lock = threading.RLock()
        self.selected = None
        self.request = None
        self.request_at = 0.0
        self.last_report = 0.0
        self.last_frame = None
        self.last_delivery = 0.0
        self.last_error = None
        self.manifests = {}
        self.pairing_override = None
        self.startup_complete = False

    def finish_startup(self):
        """Leave the firmware hourglass only after installed products become ready."""
        if self.startup_complete:
            return True
        try:
            request = Request("http://127.0.0.1:8123/ready", b"{}",
                              {"Content-Type": "application/json",
                               "X-Router-Token": TOKEN.read_text().strip()}, method="POST")
            with urlopen(request, timeout=2) as response:
                self.startup_complete = response.status == 200 and json.load(response).get("delivered") is True
        except (OSError, ValueError):
            return False
        return self.startup_complete

    def begin_pairing(self, identity, pin):
        if len(identity) != 7 or len(pin) != 6:
            raise ValueError('Invalid physical confirmation.')
        with self.lock:
            self.pairing_override = {'identity': identity, 'pin': pin, 'at': self.clock()}
            self.last_frame = None
        self.tick()
        return self.status()['delivered']

    def clear_pairing(self):
        with self.lock:
            self.pairing_override = None
            self.last_frame = None

    @staticmethod
    def _send(rows: list[str]) -> bool:
        request = Request("http://127.0.0.1:8123/frame",
                          json.dumps({"rows": rows}).encode(),
                          {"Content-Type": "application/json",
                           "X-Router-Token": TOKEN.read_text().strip()}, method="POST")
        with urlopen(request, timeout=2) as response:
            return response.status == 200 and json.load(response).get("delivered") is True

    def select(self, app: str | None) -> None:
        with self.lock:
            self.selected = app
            self.request = None
            self.last_frame = None

    def submit(self, message: dict) -> dict:
        validate_request(message)
        with self.lock:
            if message["app"] != self.selected:
                return {"accepted": False, "error": "That app does not own the Matrix."}
            if message["action"] == "clear":
                self.request = None
                self.last_frame = None
                return {"accepted": True}
            if message["action"] == "play":
                app = message["app"]
                manifest = load_manifest(MANIFESTS[app], app)
                self.manifests[app] = manifest
                if message["animation"] not in manifest["animations"]:
                    raise ValueError("Unknown Matrix animation")
            if self.request == message:
                self.last_report = self.clock()
                return {"accepted": True}
            self.request = message
            self.request_at = self.clock()
            self.last_report = self.request_at
            self.last_frame = None
            return {"accepted": True}

    def frame(self, now: float | None = None) -> list[str] | None:
        now = self.clock() if now is None else now
        with self.lock:
            if self.pairing_override:
                override = self.pairing_override
                elapsed = now - override['at']
                if elapsed < 120:
                    segments = ['ID', override['identity'][:3], override['identity'][3:6],
                                override['identity'][6:], 'PN', override['pin'][:3], override['pin'][3:]]
                    return code_frame(segments[int(elapsed / .9) % len(segments)])
                self.pairing_override = None
            message = self.request
            if not message or message["app"] != self.selected:
                return None
            if message["action"] in ("play", "status") and now - self.last_report > 5:
                self.request = None
                self.last_frame = None
                return None
            elapsed_ms = max(0, int((now - self.request_at) * 1000))
            if message["action"] == "pairing":
                if elapsed_ms >= 120_000:
                    self.request = None
                    return None
                identity, pin = message["identity"], message["pin"]
                segments = ["ID", identity[:3], identity[3:6], identity[6:],
                            "PN", pin[:3], pin[3:]]
                return code_frame(segments[(elapsed_ms // 900) % len(segments)])
            if message["action"] == "status":
                return code_frame(message["text"])
            if message["action"] != "play":
                return None
            animation = self.manifests[message["app"]]["animations"][message["animation"]]
            frames = animation["frames"]
            total = sum(frame["ms"] for frame in frames)
            position = elapsed_ms % total if animation["loop"] else min(elapsed_ms, total - 1)
            for frame in frames:
                if position < frame["ms"]:
                    return frame["rows"]
                position -= frame["ms"]
            return frames[-1]["rows"]

    def tick(self) -> None:
        now = self.clock()
        rows = self.frame(now)
        if rows is None:
            return
        signature = tuple(rows)
        with self.lock:
            if signature == self.last_frame and now - self.last_delivery < .8:
                return
        try:
            delivered = self.send(rows)
            if not delivered:
                raise OSError("The Matrix rejected the frame")
            with self.lock:
                self.last_frame = signature
                self.last_delivery = now
                self.last_error = None
        except (OSError, ValueError) as exc:
            with self.lock:
                self.last_error = str(exc)

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(.05)

    def status(self) -> dict:
        with self.lock:
            return {"selected": self.selected, "delivered": bool(self.last_delivery and
                    self.clock() - self.last_delivery < 2 and not self.last_error),
                    "error": self.last_error}
