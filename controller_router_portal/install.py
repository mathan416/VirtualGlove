#!/usr/bin/env python3
"""Install or upgrade the shared UNO Q launcher as the arduino user."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

try:
    from .host.broker import APPS, ENTRY_PROJECT, app_listing, configure_ports
    from .host.matrix_port import _matrix_loopback_compose, configure_loopback, matrix_port_lock
except ImportError:  # Direct installation from a verified release package.
    from host.broker import APPS, ENTRY_PROJECT, app_listing, configure_ports
    from host.matrix_port import _matrix_loopback_compose, configure_loopback, matrix_port_lock


SOURCE = Path(__file__).resolve().parent
HOME = Path("/home/arduino")
DEST = HOME / ".local/share/controller-router-portal"
LEGACY = HOME / "ArduinoApps/controller-router-portal"
SERVICE = HOME / ".config/systemd/user/controller-router-portal.service"
PRODUCT_SERVICE = HOME / ".config/systemd/user/controller-router-products.service"
MATRIX = HOME / "ArduinoApps/controller-router"
MATRIX_STATE = HOME / ".local/state/controller-router"


def wait_secure_setup():
    """Wait for the secure server independently of port 80 readiness."""
    import ssl
    for _ in range(30):
        try:
            with urlopen('https://127.0.0.1:8444/api/connections', timeout=2,
                         context=ssl._create_unverified_context()) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('Controller Router secure Setup did not become available.')


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
    try:
        os.replace(staged, MATRIX)
    except BaseException:
        if backup.exists():
            os.replace(backup, MATRIX)
        raise
    return (backup if backup.exists() else None), True



def start_shared_matrix(lock_held=False) -> None:
    print("Building and starting the Controller Router Matrix app; the first install may take a few minutes.", flush=True)
    command("arduino-app-cli", "app", "start", str(MATRIX))
    compose = MATRIX / ".cache/app-compose.yaml"
    configure_loopback(compose, MATRIX_STATE / ".matrix-port.lock", lock_held=lock_held)
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
    for app in APPS.values():
        if not (app['path'] / 'app.yaml').exists():
            continue
        data = app['path'] / 'data'
        data.mkdir(parents=True, exist_ok=True)
        capability = data / 'router-pairing-adapter-token'
        if not capability.exists():
            capability.write_text(secrets.token_urlsafe(48) + '\n')
            capability.chmod(0o600)
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


QUIET_UPDATE_FILES = (Path("install.py"), Path("host/products.py"))


def matching_static_payload(source: Path, installed: Path, *, exclude_quiet_updates=False) -> bool:
    """Check every packaged file without treating App Lab caches as package files."""
    for file in source.rglob("*"):
        relative = file.relative_to(source)
        if exclude_quiet_updates and relative in QUIET_UPDATE_FILES:
            continue
        if (set(relative.parts) & {".cache", "__pycache__"}
                or file.name.endswith(".pyc") or file.name.startswith("._")
                or file.name == ".DS_Store"):
            continue
        if file.is_symlink():
            return False
        if file.is_file():
            peer = installed / relative
            if peer.is_symlink() or not peer.is_file() or file.read_bytes() != peer.read_bytes():
                return False
    return True


def replace_static_file(path: Path, content: bytes, mode: int) -> None:
    """Replace one code file atomically, leaving the old file on staging failure."""
    descriptor, name = tempfile.mkstemp(prefix=".router-update-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        staged.chmod(mode)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def healthy_installed_portal() -> bool:
    """Require the private running Matrix and live chooser before a quiet install."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             "{{json .State.Running}}|{{json .HostConfig.PortBindings}}",
             "controller-router-main-1"], text=True, capture_output=True, timeout=5)
        if result.returncode:
            return False
        running, bindings = (json.loads(part) for part in result.stdout.strip().split("|", 1))
        if running is not True or bindings != {"8123/tcp": [
                {"HostIp": "127.0.0.1", "HostPort": "8123"}]}:
            return False
        for url in ("http://127.0.0.1:8123/health", "http://127.0.0.1/api/state"):
            with urlopen(url, timeout=2) as response:
                if response.status != 200:
                    return False
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def _safe_command_output(output: str) -> str:
    """Keep useful command diagnostics without echoing common credentials."""
    output = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                    "[private key redacted]", output, flags=re.DOTALL)
    lines = []
    in_private_key = False
    for line in output.splitlines():
        if re.search(r"-----BEGIN [^-]*PRIVATE KEY-----", line):
            in_private_key = True
            lines.append("[private key redacted]")
            continue
        if in_private_key:
            if re.search(r"-----END [^-]*PRIVATE KEY-----", line):
                in_private_key = False
            continue
        if re.search(r"(?i)(token|password|passwd|passphrase|secret|authorization|bearer|credential|private.?key|pairing.?code|cookie)", line):
            lines.append("[sensitive diagnostic redacted]")
            continue
        line = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", line)
        # Tokens can also appear alone or as unlabelled command arguments.
        line = re.sub(r"(?<![A-Za-z0-9_/-])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9_/-])",
                      "[long value redacted]", line)
        lines.append(line)
    return "\n".join(lines).strip()[-3000:]


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/1000",
               DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus")
    result = subprocess.run(args, env=env, check=False, text=True, capture_output=True)
    if check and result.returncode:
        # App Lab's on-board uploader sends OpenOCD diagnostics to stdout.
        # Never expose arbitrary subprocess stdout, which may contain private data.
        stdout = ""
        if args[:3] == ("arduino-app-cli", "app", "start"):
            allowed = (line for line in (result.stdout or "").splitlines()
                       if re.match(r"(?i)^\s*(?:open on-chip debugger|openocd:|error:|warn(?:ing)?\s*:|error running openocd|\*\* programming failed)", line))
            stdout = _safe_command_output("\n".join(allowed))
        stderr = _safe_command_output(result.stderr or "")
        detail = "\n".join(f"{name}: {value}" for name, value in
                           (("stdout", stdout), ("stderr", stderr)) if value)
        raise RuntimeError(f"{Path(args[0]).name} failed (exit {result.returncode}): {detail}")
    return result


def validate_package(source: Path) -> None:
    """Reject incomplete bundles before replacing a working launcher."""
    required = ("host/portal-compose.yaml", "host/products.py", "host/broker.py", "host/matrix_port.py",
                "host/controller-router-portal.service", "host/controller-router-products.service",
                "app/VERSION", "app/app.yaml", "app/python/main.py",
                "app/sketch/sketch.ino", "app/sketch/sketch.yaml",
                "python/main.py", "python/index.html", "python/setup.html", "python/trust.html",
                "python/help.html",
                "host/pairing.py", "host/secure_pairing.py", "host/pairing.html", "shared/pairing.py",
                "python/assets/pixel-pal.png", "python/assets/buddy.png")
    missing = [name for name in required if not (source / name).is_file()
               or (source / name).stat().st_size == 0]
    if missing:
        raise RuntimeError("Incomplete Controller Router launcher package: " + ", ".join(missing))


def restore_services() -> None:
    """Restore unit definitions and both services from the recovered launcher."""
    for unit in (SERVICE, PRODUCT_SERVICE):
        saved = DEST / 'host' / unit.name
        if saved.is_file():
            shutil.copy2(saved, unit)
    command('systemctl', '--user', 'daemon-reload', check=False)
    command('systemctl', '--user', 'start', SERVICE.name, check=False)
    command('systemctl', '--user', 'start', PRODUCT_SERVICE.name, check=False)


def retire_early_start() -> None:
    """Retire only the legacy VirtualGlove boot helper after Router is running."""
    units = HOME / ".config/systemd/user"
    removed_unit = False
    for name in ("virtualglove-early-start.service", "virtualglove-early-start-trial.service"):
        path = units / name
        if not (path.exists() or path.is_symlink()):
            continue
        command("systemctl", "--user", "disable", "--now", name, check=False)
        path.unlink()
        removed_unit = True
        command("systemctl", "--user", "reset-failed", name, check=False)
    helper = HOME / ".local/lib/virtualglove/uno-q-early-start.py"
    if helper.exists() or helper.is_symlink():
        helper.unlink()
    if removed_unit:
        command("systemctl", "--user", "daemon-reload")


def install() -> str:
    if os.geteuid() != 1000:
        raise RuntimeError("Install the UNO Q launcher as the arduino user.")
    newer = next((root for root in (DEST, LEGACY)
                  if root.exists() and version(root) > version(SOURCE)), None)
    if newer is not None:
        # Keep the newer shared software, but register a product just installed
        # by this older bundle. Product data and existing assignments stay put.
        command("python3", str(newer / "host/products.py"), "start-all")
        command("systemctl", "--user", "enable", "--now", SERVICE.name)
        command("systemctl", "--user", "enable", "--now", PRODUCT_SERVICE.name)
        retire_early_start()
        return "Kept the newer Controller Router launcher and started installed controller services."
    validate_package(SOURCE)
    if (DEST.is_dir() and version(DEST) == version(SOURCE)
            and all((SOURCE / name).is_file() and not (SOURCE / name).is_symlink()
                    and (DEST / name).is_file() and not (DEST / name).is_symlink()
                    for name in QUIET_UPDATE_FILES)
            and matching_static_payload(SOURCE, DEST, exclude_quiet_updates=True)
            and healthy_installed_portal()):
        # Product upgrades bundle Router too. An identical, healthy Router needs
        # only product registration. The installer and product launcher can be
        # refreshed together without invoking App Lab or stopping Matrix.
        with tempfile.TemporaryDirectory(prefix=".router-quiet-update-", dir=DEST.parent) as backup_dir:
            changed = []
            try:
                for name in QUIET_UPDATE_FILES:
                    source_file, installed_file = SOURCE / name, DEST / name
                    if source_file.read_bytes() == installed_file.read_bytes():
                        continue
                    backup = Path(backup_dir) / name
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(installed_file, backup)
                    replace_static_file(installed_file, source_file.read_bytes(),
                                        stat.S_IMODE(source_file.stat().st_mode))
                    changed.append((installed_file, backup))
                command("python3", str(DEST / "host/products.py"), "start-all")
                command("systemctl", "--user", "enable", "--now", SERVICE.name)
                command("systemctl", "--user", "enable", "--now", PRODUCT_SERVICE.name)
                retire_early_start()
            except BaseException:
                for installed_file, backup in reversed(changed):
                    replace_static_file(installed_file, backup.read_bytes(),
                                        stat.S_IMODE(backup.stat().st_mode))
                raise
        return "Kept the healthy Controller Router launcher and started installed controller services."
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
    with matrix_port_lock(MATRIX_STATE / ".matrix-port.lock"):
        try:
            try:
                from .host.secure_pairing import certificates
            except ImportError:
                from host.secure_pairing import certificates
            certificates(MATRIX_STATE)
            for app_id, app in APPS.items():
                if listing.get(app["name"]) == "running":
                    command("arduino-app-cli", "app", "stop", str(app["path"]))
            matrix_backup, changed = install_matrix_app()
            if changed or app_listing().get("Controller Router") != "running":
                start_shared_matrix(lock_held=True)
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
            wait_secure_setup()
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
            if previous_default and Path(previous_default).is_dir():
                command("arduino-app-cli", "app", "start", previous_default, check=False)
                command("arduino-app-cli", "properties", "set", "default", previous_default, check=False)
            if had_portal:
                restore_services()
            raise
    retire_early_start()
    if LEGACY.is_dir():
        saved = DEST.with_name(DEST.name + ".app-lab-backup")
        suffix = 1
        while saved.exists():
            saved = DEST.with_name(DEST.name + f".app-lab-backup-{suffix}")
            suffix += 1
        os.replace(LEGACY, saved)
    try:
        from .host.secure_pairing import certificates, lan_addresses
        from .shared.pairing import fingerprint
    except ImportError:
        from host.secure_pairing import certificates, lan_addresses
        from shared.pairing import fingerprint
    import ssl, socket
    cert, _ = certificates(MATRIX_STATE)
    print('Secure Setup certificate SHA-256: ' + fingerprint(ssl.PEM_cert_to_DER_cert(cert.read_text())), flush=True)
    hostname = socket.gethostname().split('.')[0] + '.local'
    print('Pair console: http://' + hostname + '/pair', flush=True)
    print('Secure Setup: https://' + hostname + ':8444/setup', flush=True)
    for address in lan_addresses():
        print('Pair console: http://' + address + '/pair', flush=True)
        print('Secure Setup: https://' + address + ':8444/setup', flush=True)
    return "Controller Router launcher and shared Matrix installed; product services remain online."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(install())
