"""UNO Q user service controlling only the two approved App Lab controllers."""
from __future__ import annotations

import json
import os
import re
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
MATRIX_STATE = Path("/home/arduino/.local/state/controller-router")
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
    from .matrix_port import configure_loopback, matrix_port_lock
    from .products import entry_environment
except ImportError:  # Executed from the installed host script.
    from concurrent import ConcurrentLauncher
    from matrix_port import configure_loopback, matrix_port_lock
    from products import entry_environment

# App Lab images, updates and installs all land on the UNO Q's ~10 GB system
# disk. Below this, an install or App Lab update can fail part-way.
LOW_DISK_BYTES = 1024 ** 3


def system_disk(path: str = "/") -> dict | None:
    """Report free space on the system disk, as the arduino user can use it."""
    try:
        info = os.statvfs(path)
    except OSError:
        return None
    free = info.f_bavail * info.f_frsize
    return {"free": free, "total": info.f_blocks * info.f_frsize, "low": free < LOW_DISK_BYTES}


LAUNCHER = ConcurrentLauncher()
PAIRING = None


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            message = json.loads(self.rfile.readline(32769))
            action = message.get("action")
            if action == "state":
                result = LAUNCHER.state()
                disk = system_disk()
                if disk is not None:
                    result = dict(result, disk=disk)
            elif action == 'connections' and PAIRING is not None:
                result = PAIRING.inspect()
            elif action == 'console-halt' and PAIRING is not None:
                # A paired console's signed shutdown request; PairingManager verifies it.
                result = PAIRING.console_halt(message)
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


def portal_ready() -> bool:
    """Check the entry page itself, rather than only Docker's container state."""
    try:
        with urlopen("http://127.0.0.1/api/state", timeout=2) as response:
            state = json.load(response)
        return response.status == 200 and isinstance(state, dict) and "apps" in state and "matrix" in state
    except (OSError, ValueError, TypeError):
        return False


def ensure_portal() -> None:
    """Start the entry page once and wait until its Router API responds."""
    if portal_ready():
        return
    compose = PORTAL / "host/portal-compose.yaml"
    if not compose.is_file():
        raise FileNotFoundError(f"Controller Router entry configuration is missing: {compose}")
    try:
        subprocess.run(["docker", "compose", "-p", ENTRY_PROJECT, "-f", str(compose),
                        "up", "-d"], env=entry_environment(), check=True,
                       capture_output=True, text=True, timeout=90)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        raise RuntimeError("Controller Router entry did not start: " +
                           (detail[-1][:500] if detail else str(exc))) from exc
    for _ in range(10):
        if portal_ready():
            return
        time.sleep(1)
    raise RuntimeError("Controller Router entry started but port 80 did not respond.")


def start_portal() -> None:
    """Restore only the entry page; never restart Docker while a game may be active."""
    last_error = None
    while True:
        try:
            ensure_portal()
            last_error = None
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            message = str(exc)
            if message != last_error:
                print("Controller Router entry unavailable: " + message, flush=True)
                last_error = message
        time.sleep(15)


def ensure_matrix_port() -> bool:
    """Restore loopback access after App Lab regenerates an unexposed app."""
    matrix = ROOT / "controller-router"
    descriptor = matrix / "app.yaml"
    compose = matrix / ".cache/app-compose.yaml"
    lock = MATRIX_STATE / ".matrix-port.lock"
    with matrix_port_lock(lock):
        if not descriptor.is_file() or not compose.is_file():
            return False
        # App Lab must not itself publish this app: otherwise it can expose the
        # port before this watchdog has a chance to patch the generated Compose.
        if re.search(r"(?m)^ports\s*:", descriptor.read_text()):
            raise RuntimeError("Matrix descriptor must not publish a port")
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "controller-router-main-1"],
            check=False, text=True, capture_output=True, timeout=10)
        if result.returncode or result.stdout.strip() != "true":
            return False
        binding = subprocess.run(
            ["docker", "inspect", "--format", '{{json (index .NetworkSettings.Ports "8123/tcp")}}',
             "controller-router-main-1"], check=False, text=True, capture_output=True, timeout=10)
        if binding.returncode:
            return False
        try:
            ports = json.loads(binding.stdout)
        except ValueError as exc:
            raise RuntimeError("Cannot inspect Matrix port binding") from exc
        expected = [{"HostIp": "127.0.0.1", "HostPort": "8123"}]
        if ports == expected:
            return False
        return configure_loopback(compose, lock, force=True, lock_held=True,
                                  safe_to_restart=lambda: not matrix_recreation_unsafe())


def matrix_recreation_unsafe() -> bool:
    """Defer if any installed product cannot positively report an idle game."""
    for app_id, app in APPS.items():
        if not (app["path"] / "app.yaml").is_file():
            continue
        try:
            with urlopen(app["url"], timeout=3) as response:
                state = json.load(response)
            key = "game_session_active" if app_id == "virtualglove" else "live_game_active"
            if not isinstance(state, dict) or not isinstance(state.get(key), bool) or state[key]:
                return True
        except (OSError, ValueError, TypeError):
            return True
    return False


def reconcile_matrix_port(game_active) -> None:
    """Retry after boot or an App Lab restart, without interrupting gameplay."""
    last_error = None
    while True:
        try:
            if not game_active():
                ensure_matrix_port()
            last_error = None
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            message = str(exc)
            if message != last_error:
                print("Controller Router Matrix port unavailable: " + message, flush=True)
                last_error = message
        time.sleep(15)


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
    def matrix_game_active():
        return matrix_recreation_unsafe()
    PAIRING = PairingManager(LAUNCHER.matrix, game_active)
    def reconcile():
        while True:
            try:
                if game_active():
                    PAIRING.close_window()
                PAIRING.reconcile()
            except (OSError, ValueError):
                pass
            time.sleep(15)
    threading.Thread(target=reconcile, daemon=True, name='router-connections').start()
    threading.Thread(target=reconcile_matrix_port, args=(matrix_game_active,), daemon=True,
                     name='router-matrix-port').start()
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
