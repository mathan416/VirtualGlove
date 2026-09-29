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


try:
    from .concurrent import ConcurrentLauncher
except ImportError:  # Executed from the installed host script.
    from concurrent import ConcurrentLauncher

LAUNCHER = ConcurrentLauncher()
PAIRING = None


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            message = json.loads(self.rfile.readline(32769))
            action = message.get("action")
            if action == "state":
                result = LAUNCHER.state()
            elif action == 'connections' and PAIRING is not None:
                result = PAIRING.inspect()
            elif action == 'pairing-certificate':
                try:
                    from .secure_pairing import public_certificate
                    from .pairing import STATE
                except ImportError:
                    from secure_pairing import public_certificate
                    from pairing import STATE
                result = public_certificate(STATE)
            elif action == "routing":
                try:
                    from .routing import routing
                except ImportError:
                    from routing import routing
                if PAIRING is not None and PAIRING.inspect()['consoles']:
                    result = PAIRING.routing(message)
                else:
                    result = routing(message, LAUNCHER.state())
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
    global PAIRING
    try:
        from .pairing import PairingManager, STATE
        from .secure_pairing import serve as serve_pairing
    except ImportError:
        from pairing import PairingManager, STATE
        from secure_pairing import serve as serve_pairing
    def game_active():
        return any(app.get('game_active') for app in LAUNCHER.state().get('apps', {}).values())
    PAIRING = PairingManager(LAUNCHER.matrix, game_active)
    def reconcile():
        while True:
            try:
                if game_active():
                    PAIRING.cancel()
                PAIRING.reconcile()
            except (OSError, ValueError):
                pass
            time.sleep(15)
    threading.Thread(target=reconcile, daemon=True, name='router-connections').start()
    threading.Thread(target=serve_pairing, args=(PAIRING, STATE), daemon=True,
                     name='router-secure-setup').start()
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
