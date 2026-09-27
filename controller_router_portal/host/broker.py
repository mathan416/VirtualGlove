"""UNO Q user service controlling only the two approved App Lab controllers."""
from __future__ import annotations

import json
import os
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path("/home/arduino/ArduinoApps")
SOCKET_DIR = Path("/run/user/1000/controller-router-portal")
SOCKET = SOCKET_DIR / "control.sock"
APPS = {
    "virtualglove": {"name": "VirtualGlove", "path": ROOT / "virtualglove",
                     "url": "http://127.0.0.1:8100/status", "port": 8100},
    "rob_vision": {"name": "R.O.B. Vision", "path": ROOT / "rob-vision",
                   "url": "http://127.0.0.1:8101/api/state", "port": 8101},
}
PORTAL = Path("/home/arduino/.local/share/controller-router-portal")
ENTRY_PROJECT = "uno-controller-router-entry"


def cli(*args: str, timeout: int = 360) -> str:
    result = subprocess.run(["arduino-app-cli", *args], text=True, capture_output=True,
                            timeout=timeout, check=True)
    return result.stdout


def app_listing() -> dict[str, str]:
    data = json.loads(cli("app", "list", "--format", "json", timeout=15))
    return {item["name"]: item.get("status", "unknown") for item in data.get("apps", [])}


def installed(app_id: str, listing: dict[str, str]) -> bool:
    app = APPS[app_id]
    return app["path"].joinpath("app.yaml").is_file() and app["name"] in listing


def health(app_id: str) -> tuple[bool, bool]:
    """Return service readiness and whether a live game owns controls."""
    try:
        with urlopen(APPS[app_id]["url"], timeout=3) as response:
            state = json.load(response)
        if app_id == "virtualglove":
            ready = bool(state.get("worker_running")) and state.get("firmware", {}).get("state") == "matched"
            return ready, bool(state.get("game_session_active"))
        with urlopen("http://127.0.0.1:8101/api/matrix/state", timeout=3) as response:
            matrix = json.load(response)
        return bool(matrix.get("available") and matrix.get("bridge_ok")), bool(state.get("live_game_active"))
    except (OSError, ValueError, TypeError):
        return False, False


def configure_ports(app_id: str) -> None:
    """Move browser exposure while retaining established private API ports."""
    app = APPS[app_id]
    compose = app["path"] / ".cache/app-compose.yaml"
    source = compose.read_text()
    lines = source.splitlines(keepends=True)
    if app_id == "virtualglove":
        anchor = "- 8088:8088"
        replacements = ("- 127.0.0.1:8088:8088", "- 8100:8088")
    else:
        anchor = "- 8766:8766"
        replacements = ("- 8766:8766", "- 8101:8766")
    fresh = any(line.strip() == anchor for line in lines)
    if not fresh and not all(any(line.strip() == item for line in lines) for item in replacements):
        raise RuntimeError("App Lab did not generate the expected controller port.")
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped in {"- 80:80", "- 80:8088"}:
            continue
        if fresh and stripped in {"- 8100:8088", "- 8101:8766", "- 127.0.0.1:8088:8088"}:
            continue
        if fresh and stripped == anchor:
            indent = line[:len(line) - len(line.lstrip())]
            output.extend(indent + item + "\n" for item in replacements)
            continue
        output.append(line)
    changed = "".join(output)
    if changed != source:
        temporary = compose.with_name(".app-compose.portal.tmp")
        temporary.write_text(changed)
        os.replace(temporary, compose)
        env = dict(os.environ, APP_HOME=str(app["path"]))
        subprocess.run(["docker", "compose", "-p", app["path"].name, "-f", str(compose),
                        "up", "-d", "--force-recreate", "main"], env=env, check=True,
                       text=True, capture_output=True, timeout=90)


class Launcher:
    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.error = ""
        self.target = None

    def state(self) -> dict:
        listing = app_listing()
        apps = {}
        for app_id, app in APPS.items():
            present = installed(app_id, listing)
            running = present and listing.get(app["name"]) == "running"
            ready, game = health(app_id) if running else (False, False)
            apps[app_id] = {"installed": present, "running": running,
                            "ready": ready, "game_active": game, "port": app["port"]}
        with self.lock:
            return {"apps": apps, "busy": self.busy, "target": self.target, "error": self.error}

    def select(self, app_id: str) -> dict:
        if app_id not in APPS:
            return {"error": "Unknown controller app."}
        state = self.state()
        if not state["apps"][app_id]["installed"]:
            return {"error": "That controller app is not installed."}
        with self.lock:
            if self.busy:
                return {"error": "A controller switch is already in progress."}
            self.busy, self.target, self.error = True, app_id, ""
        threading.Thread(target=self._switch, args=(app_id,), daemon=True).start()
        return {"accepted": True}

    def _switch(self, target: str) -> None:
        previous = None
        try:
            listing = app_listing()
            running = [key for key, app in APPS.items() if listing.get(app["name"]) == "running"]
            for key in running:
                ready, game = health(key)
                if not ready:
                    raise RuntimeError("The running controller is unavailable; recover it locally before switching.")
                if game:
                    raise RuntimeError("End the current game before switching controllers.")
            previous = next((key for key in running if key != target), None)
            for key in running:
                if key != target:
                    cli("app", "stop", str(APPS[key]["path"]))
            if target not in running:
                cli("app", "start", str(APPS[target]["path"]))
            configure_ports(target)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                ready, _ = health(target)
                if ready:
                    cli("properties", "set", "default", str(APPS[target]["path"]), timeout=20)
                    return
                if app_listing().get(APPS[target]["name"]) == "failed":
                    raise RuntimeError("App Lab could not start the selected controller.")
                time.sleep(2)
            raise RuntimeError("The selected controller did not become ready.")
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            message = str(exc)
            if previous:
                try:
                    cli("app", "stop", str(APPS[target]["path"]), timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass
                try:
                    cli("app", "start", str(APPS[previous]["path"]))
                    configure_ports(previous)
                    cli("properties", "set", "default", str(APPS[previous]["path"]), timeout=20)
                except (OSError, subprocess.SubprocessError):
                    message += " The previous controller could not be restored automatically."
            with self.lock:
                self.error = message
        finally:
            with self.lock:
                self.busy, self.target = False, None


if (ROOT / "controller-router/app.yaml").is_file():
    try:
        from .concurrent import ConcurrentLauncher
    except ImportError:
        from concurrent import ConcurrentLauncher
    LAUNCHER = ConcurrentLauncher()
else:
    LAUNCHER = Launcher()


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            message = json.loads(self.rfile.readline(1024))
            action = message.get("action")
            if action == "state":
                result = LAUNCHER.state()
            elif action == "select":
                result = LAUNCHER.select(message.get("app"))
            elif action == "display" and hasattr(LAUNCHER, "display"):
                result = LAUNCHER.display(message.get("request"))
            elif action == "lease" and hasattr(LAUNCHER, "lease"):
                result = LAUNCHER.lease(message.get("app"))
            else:
                result = {"error": "Unsupported action."}
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
            result = {"error": str(exc)}
        self.wfile.write((json.dumps(result) + "\n").encode())


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def start_portal() -> None:
    for _ in range(40):
        try:
            if PORTAL.joinpath("host/portal-compose.yaml").is_file():
                subprocess.run(["docker", "compose", "-p", ENTRY_PROJECT,
                                "-f", str(PORTAL / "host/portal-compose.yaml"),
                                "up", "-d", "--force-recreate"], check=True,
                               capture_output=True, text=True, timeout=90)
            return
        except (OSError, subprocess.SubprocessError, ValueError):
            time.sleep(3)


def main() -> None:
    SOCKET_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    SOCKET_DIR.chmod(0o700)
    try:
        SOCKET.unlink()
    except FileNotFoundError:
        pass
    with Server(str(SOCKET), Handler) as server:
        SOCKET.chmod(0o600)
        threading.Thread(target=start_portal, daemon=True).start()
        server.serve_forever()


if __name__ == "__main__":
    main()
