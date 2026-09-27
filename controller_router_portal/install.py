#!/usr/bin/env python3
"""Install or upgrade the shared UNO Q launcher as the arduino user."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

try:
    from .host.broker import APPS, ENTRY_PROJECT, app_listing, configure_ports
except ImportError:  # Direct installation from a verified release package.
    from host.broker import APPS, ENTRY_PROJECT, app_listing, configure_ports


SOURCE = Path(__file__).resolve().parent
HOME = Path("/home/arduino")
DEST = HOME / ".local/share/controller-router-portal"
LEGACY = HOME / "ArduinoApps/controller-router-portal"
SERVICE = HOME / ".config/systemd/user/controller-router-portal.service"
PRODUCT_SERVICE = HOME / ".config/systemd/user/controller-router-products.service"
MATRIX = HOME / "ArduinoApps/controller-router"
MATRIX_STATE = HOME / ".local/state/controller-router"


def install_matrix_app() -> tuple[Path | None, bool]:
    """Install the only active App Lab sketch without touching product data."""
    source = SOURCE / "app"
    if not (source / "sketch/sketch.ino").is_file() or not (source / "sketch/sketch.yaml").is_file():
        raise RuntimeError("Controller Router Matrix sketch or build profile is missing")
    if (MATRIX / "data/matrix-token").is_file() and all(
        (MATRIX / name).is_file() and (MATRIX / name).read_bytes() == (source / name).read_bytes()
        for name in ("VERSION", "app.yaml", "sketch/sketch.ino", "sketch/sketch.yaml", "python/main.py")
    ):
        return None, False
    MATRIX_STATE.mkdir(parents=True, exist_ok=True)
    backup = MATRIX_STATE / "matrix-before-upgrade"
    if backup.exists():
        shutil.rmtree(backup)
    staged = MATRIX_STATE / "matrix-stage"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(source, staged)
    (staged / "data").mkdir(exist_ok=True)
    token = staged / "data/matrix-token"
    old_token = MATRIX / "data/matrix-token"
    token.write_text(old_token.read_text() if old_token.is_file() else secrets.token_urlsafe(48) + "\n")
    token.chmod(0o600)
    if MATRIX.exists():
        command("arduino-app-cli", "app", "stop", str(MATRIX), check=False)
        os.replace(MATRIX, backup)
    os.replace(staged, MATRIX)
    return (backup if backup.exists() else None), True


def start_shared_matrix() -> None:
    command("arduino-app-cli", "app", "start", str(MATRIX))
    compose = MATRIX / ".cache/app-compose.yaml"
    original = compose.read_text()
    replaced = original.replace("- 8123:8123", "- 127.0.0.1:8123:8123")
    if replaced == original and "- 127.0.0.1:8123:8123" not in original:
        raise RuntimeError("App Lab did not create the expected Matrix service port")
    if replaced != original:
        compose.write_text(replaced)
        command("docker", "compose", "-p", "controller-router", "-f", str(compose),
                "up", "-d", "--force-recreate", "main")
    command("arduino-app-cli", "properties", "set", "default", str(MATRIX))
    for _ in range(45):
        try:
            with urlopen("http://127.0.0.1:8123/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(2)
    raise RuntimeError("The shared Matrix service did not start")


def start_products() -> None:
    try:
        from .host.products import start
    except ImportError:
        from host.products import start
    for product in ("virtualglove", "rob-vision"):
        if (HOME / "ArduinoApps" / product / "app.yaml").is_file():
            lease = HOME / "ArduinoApps" / product / "data/controller-router-lease.json"
            lease.parent.mkdir(exist_ok=True)
            lease.write_text('{"schema":1,"active":false,"until":0}\n')
            lease.chmod(0o600)
            start(product)


def version(root: Path) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in (root / "VERSION").read_text().strip().split("."))
    except (OSError, ValueError):
        return ()


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/1000",
               DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus")
    result = subprocess.run(args, env=env, check=False, text=True, capture_output=True)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise RuntimeError(f"{' '.join(args[:3])} failed: {detail}")
    return result


def install() -> str:
    if os.geteuid() != 1000:
        raise RuntimeError("Install the UNO Q launcher as the arduino user.")
    if not SOURCE.joinpath("host/portal-compose.yaml").is_file():
        raise RuntimeError("Incomplete Controller Router launcher package.")
    newer = next((root for root in (DEST, LEGACY)
                  if root.exists() and version(root) > version(SOURCE)), None)
    if newer is not None:
        # Keep the newer shared software, but register a product just installed
        # by this older bundle. Product data and existing assignments stay put.
        command("python3", str(newer / "host/products.py"), "start-all")
        command("systemctl", "--user", "enable", "--now", SERVICE.name)
        command("systemctl", "--user", "enable", "--now", PRODUCT_SERVICE.name)
        return "Kept the newer Controller Router launcher and started installed controller services."
    DEST.parent.mkdir(parents=True, exist_ok=True)
    listing = app_listing()
    for app_id, app in APPS.items():
        if not (app["path"] / "app.yaml").is_file():
            continue
        old_port = 8100 if app_id == "virtualglove" else 8101
        old_path = "/status" if app_id == "virtualglove" else "/api/state"
        try:
            with urlopen(f"http://127.0.0.1:{old_port}{old_path}", timeout=3) as response:
                state = json.load(response)
        except (OSError, ValueError):
            if listing.get(app["name"]) != "running":
                continue
            # Older installations expose only their original service port.
            old_port = 8088 if app_id == "virtualglove" else 8766
            try:
                with urlopen(f"http://127.0.0.1:{old_port}{old_path}", timeout=3) as response:
                    state = json.load(response)
            except (OSError, ValueError):
                raise RuntimeError("A running controller is unavailable; recover it before upgrading the launcher.")
        if (state.get("game_session_active") or state.get("live_game_active") or
                (state.get("game") and state.get("input", {}).get("frame_hook"))):
            raise RuntimeError("End the current game before upgrading the launcher.")
    previous_default = None
    try:
        previous_default = json.loads(command("arduino-app-cli", "properties", "get", "default",
                                              "--format", "json").stdout)["app"]["FullPath"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        pass
    old_compose = DEST / "host/portal-compose.yaml"
    if LEGACY.is_dir() and listing.get("Controller Router") == "running":
        command("arduino-app-cli", "app", "stop", str(LEGACY))
    for compose in (LEGACY / "host/portal-compose.yaml", old_compose):
        if compose.is_file():
            for project in ("controller-router-portal", ENTRY_PROJECT):
                command("docker", "compose", "-p", project, "-f",
                        str(compose), "down", check=False)
    had_portal = DEST.exists()
    with tempfile.TemporaryDirectory(prefix=".controller-router-portal-", dir=DEST.parent) as directory:
        staged = Path(directory) / DEST.name
        shutil.copytree(SOURCE, staged, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".cache", "._*", ".DS_Store"))
        portal_backup = DEST.with_name(DEST.name + ".previous")
        if portal_backup.exists():
            shutil.rmtree(portal_backup)
        if DEST.exists():
            os.replace(DEST, portal_backup)
        try:
            os.replace(staged, DEST)
        except BaseException:
            if portal_backup.exists():
                os.replace(portal_backup, DEST)
            raise
    SERVICE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEST / "host/controller-router-portal.service", SERVICE)
    shutil.copy2(DEST / "host/controller-router-products.service", PRODUCT_SERVICE)
    old_rob_yaml = APPS["rob_vision"]["path"] / "app.yaml"
    changed_rob_yaml = False
    if old_rob_yaml.is_file() and "\n  - 80\n" in old_rob_yaml.read_text():
        yaml_backup = old_rob_yaml.with_name("app.yaml.before-controller-router-portal")
        if not yaml_backup.exists():
            shutil.copy2(old_rob_yaml, yaml_backup)
        old_rob_yaml.write_text(old_rob_yaml.read_text().replace("\n  - 80\n", "\n", 1))
        changed_rob_yaml = True
    matrix_backup = None
    changed = False
    try:
        for app_id, app in APPS.items():
            if listing.get(app["name"]) == "running":
                command("arduino-app-cli", "app", "stop", str(app["path"]))
        matrix_backup, changed = install_matrix_app()
        if changed or app_listing().get("Controller Router") != "running":
            start_shared_matrix()
        # Reassert this on repeat installs too: a user may have cleared or
        # changed App Lab's startup selection since the first installation.
        command("arduino-app-cli", "properties", "set", "default", str(MATRIX))
        start_products()
        command("systemctl", "--user", "daemon-reload")
        command("systemctl", "--user", "enable", "--now", SERVICE.name)
        command("systemctl", "--user", "enable", "--now", PRODUCT_SERVICE.name)
        command("systemctl", "--user", "restart", SERVICE.name)
        for _ in range(30):
            try:
                with urlopen("http://127.0.0.1/api/state", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(2)
        else:
            raise RuntimeError("Controller Router did not become available on port 80.")
    except BaseException:
        command("systemctl", "--user", "stop", SERVICE.name, check=False)
        command("systemctl", "--user", "stop", PRODUCT_SERVICE.name, check=False)
        command("arduino-app-cli", "app", "stop", str(MATRIX), check=False)
        if changed and MATRIX.exists():
            failed = MATRIX_STATE / "matrix-failed"
            if failed.exists():
                shutil.rmtree(failed)
            os.replace(MATRIX, failed)
        if matrix_backup and matrix_backup.exists():
            os.replace(matrix_backup, MATRIX)
        if changed_rob_yaml and yaml_backup.exists():
            shutil.copy2(yaml_backup, old_rob_yaml)
        if portal_backup.exists() or not had_portal:
            failed_portal = DEST.with_name(DEST.name + ".failed")
            if failed_portal.exists():
                shutil.rmtree(failed_portal)
            if DEST.exists():
                os.replace(DEST, failed_portal)
            if portal_backup.exists():
                os.replace(portal_backup, DEST)
        if had_portal:
            command("systemctl", "--user", "start", SERVICE.name, check=False)
        if previous_default and Path(previous_default).is_dir():
            command("arduino-app-cli", "app", "start", previous_default, check=False)
            command("arduino-app-cli", "properties", "set", "default", previous_default, check=False)
        raise
    if LEGACY.is_dir():
        saved = DEST.with_name(DEST.name + ".app-lab-backup")
        suffix = 1
        while saved.exists():
            saved = DEST.with_name(DEST.name + f".app-lab-backup-{suffix}")
            suffix += 1
        os.replace(LEGACY, saved)
    return "Controller Router launcher and shared Matrix installed; product services remain online."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(install())
