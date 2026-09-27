"""One live controller lease while both UNO Q product services stay online."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.request import urlopen

try:
    from .display_runtime import MatrixScheduler
except ImportError:  # Executed from the installed host script.
    from display_runtime import MatrixScheduler

ROOT = Path("/home/arduino/ArduinoApps")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id").read_text().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else "development"
APPS = {
    "virtualglove": {"path": ROOT / "virtualglove", "url": "http://127.0.0.1:8100/status", "port": 8100},
    "rob_vision": {"path": ROOT / "rob-vision", "url": "http://127.0.0.1:8101/api/state", "port": 8101},
}


def lease_active(path: Path, now: float | None = None) -> bool:
    """Fail closed when Router is down, has rebooted, or revoked the lease."""
    try:
        data = json.loads(path.read_text())
        return (data.get("schema") == 1 and data.get("boot_id") == BOOT_ID and
                data.get("active") is True and
                isinstance(data.get("until"), (int, float)) and
                (time.monotonic() if now is None else now) < data["until"])
    except (OSError, ValueError, TypeError):
        return False


class ConcurrentLauncher:
    def __init__(self, apps=None, matrix=None, clock=time.monotonic):
        self.apps = apps or APPS
        self.matrix = matrix or MatrixScheduler()
        self.clock = clock
        self.selected = None
        self.game_owned = False
        self.lock = threading.RLock()
        self.error = ""
        self.busy = False
        self._write_leases(None)
        threading.Thread(target=self.matrix.run, daemon=True, name="router-matrix").start()
        threading.Thread(target=self._heartbeat, daemon=True, name="router-leases").start()

    def _health(self, app_id: str) -> tuple[bool, bool]:
        try:
            with urlopen(self.apps[app_id]["url"], timeout=2) as response:
                state = json.load(response)
            if app_id == "virtualglove":
                return bool(state.get("worker_running")), bool(state.get("game_session_active"))
            return True, bool(state.get("live_game_active"))
        except (OSError, ValueError, TypeError):
            return False, False

    @staticmethod
    def _matrix_ready() -> bool:
        try:
            with urlopen("http://127.0.0.1:8123/health", timeout=2) as response:
                return json.load(response).get("ready") is True
        except (OSError, ValueError, TypeError):
            return False

    def _lease_path(self, app_id: str) -> Path:
        return self.apps[app_id]["path"] / "data/controller-router-lease.json"

    def _write_leases(self, selected: str | None) -> None:
        for app_id in self.apps:
            path = self._lease_path(app_id)
            if not path.parent.is_dir():
                continue
            marker = path.with_name("controller-router-required")
            if not marker.exists():
                marker.write_text("1\n")
                marker.chmod(0o600)
            data = {"schema": 1, "boot_id": BOOT_ID, "active": app_id == selected,
                    "until": self.clock() + 2 if app_id == selected else 0}
            temporary = path.with_name(".controller-router-lease.tmp")
            temporary.write_text(json.dumps(data) + "\n")
            temporary.chmod(0o600)
            os.replace(temporary, path)

    def _heartbeat(self) -> None:
        while True:
            try:
                with self.lock:
                    self._reconcile_games()
                    self._write_leases(self.selected)
            except OSError as exc:
                with self.lock:
                    self.error = str(exc)
            time.sleep(.25)

    def _reconcile_games(self) -> None:
        """Follow authenticated product sessions without a browser selection."""
        health = {app: self._health(app) for app in self.apps}
        active = [app for app, (ready, game) in health.items() if ready and game]
        if self.selected and not health[self.selected][0]:
            self._write_leases(None)
            self.selected = None
            self.game_owned = False
            self.matrix.select(None)
        if len(active) > 1:
            self.error = "More than one controller reports a live game; end one game."
            self._write_leases(None)
            self.selected = None
            self.game_owned = False
            self.matrix.select(None)
            return
        if active:
            owner = active[0]
            if self.selected != owner:
                previous = self.selected
                self._write_leases(None)
                self.selected = None
                self.matrix.select(None)
                if previous:
                    # Neutralize the old receiver before granting another app input.
                    time.sleep(.8)
                if not self._health(owner) == (True, True):
                    return
                self._write_leases(owner)
                self.selected = owner
                self.matrix.select(owner)
            self.game_owned = True
            self.error = ""
        elif self.game_owned:
            self._write_leases(None)
            self.selected = None
            self.game_owned = False
            self.matrix.select(None)

    def state(self) -> dict:
        with self.lock:
            apps = {}
            for app_id, app in self.apps.items():
                present = (app["path"] / "app.yaml").is_file()
                ready, game = self._health(app_id) if present else (False, False)
                apps[app_id] = {"installed": present, "running": ready, "ready": ready,
                                "game_active": game, "port": app["port"],
                                "selected": self.selected == app_id}
            matrix = self.matrix.status()
            matrix["ready"] = self._matrix_ready()
            return {"apps": apps, "selected": self.selected, "busy": self.busy,
                    "target": None, "error": self.error, "matrix": matrix}

    def select(self, app_id: str) -> dict:
        if app_id not in self.apps:
            return {"error": "Unknown controller app."}
        with self.lock:
            if self.busy:
                return {"error": "Controller selection is in progress."}
            if not self._matrix_ready():
                return {"error": "The shared Matrix service is not ready."}
            if not (self.apps[app_id]["path"] / "app.yaml").is_file() or not self._health(app_id)[0]:
                return {"error": "That controller is not ready."}
            if self.selected == app_id:
                return {"accepted": True}
            if any(self._health(key)[1] for key in self.apps):
                return {"error": "End the current game before changing controllers."}
            self.busy = True
            try:
                self._write_leases(None)
                self.matrix.select(None)
                self.selected = None
                self.game_owned = False
                # Let the console receiver's existing short watchdog neutralize input.
                time.sleep(.8)
                if not self._health(app_id)[0]:
                    raise RuntimeError("The selected controller became unavailable.")
                self._write_leases(app_id)
                self.selected = app_id
                self.matrix.select(app_id)
                self.error = ""
                return {"accepted": True}
            except (OSError, RuntimeError) as exc:
                self.error = str(exc)
                self._write_leases(None)
                return {"error": self.error}
            finally:
                self.busy = False

    def display(self, message: dict) -> dict:
        with self.lock:
            if any(self._health(key)[1] for key in self.apps) and message.get("action") == "pairing":
                return {"error": "End the current game before pairing."}
            return self.matrix.submit(message)

    def lease(self, app_id: str) -> dict:
        with self.lock:
            return {"active": app_id == self.selected and lease_active(self._lease_path(app_id))}
