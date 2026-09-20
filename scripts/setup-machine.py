#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/setup-machine.py
# Purpose: Install or check Controller and supported-console integration without replacing private settings.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-19 - Kept RetroPie Controller Router available before receiver startup.
#   2026-09-11 - Adopted the virtualglove App Lab directory and conditional legacy repair.
#   2026-09-11 - Migrated App Lab containers to the virtualglove Compose project.
#   2026-09-11 - Exposed the stable host name to the containerized HTTPS server.
#   2026-09-11 - Verify the persistent local HTTPS authority and protected keys.
#   2026-09-11 - Stop safely with repair guidance for retired Raspbian Buster repositories.
#   2026-09-11 - Preserve the App Lab root during release-install Compose recreation.
#   2026-09-09 - Added the optional ROM-free RetroPie calibration test.
#   2026-09-09 - Install uhubctl for capability-gated camera-port power cycling.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-03 - Added repeatable host installers with backups and explicit health reports.
#   2026-09-03 - Install and check mDNS dependencies and boot service on both machines.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.

"""Install or check VirtualGlove on a supported Controller or console host."""
import argparse
import datetime
import json
import os
import pwd
import grp
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
UNOQ_APP = "/home/arduino/ArduinoApps/virtualglove"
BACKUPS = Path("/var/backups/virtualglove") / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
if Path("/recalbox/recalbox.version").is_file():
    BACKUPS = (Path("/recalbox/share/system/virtualglove-backups") /
               datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
elif Path("/usr/share/batocera/batocera.version").is_file():
    BACKUPS = (Path("/userdata/system/virtualglove-backups") /
               datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))


def installation_manifest():
    """Load the shared payload ownership and recovery implementation."""
    import runpy
    return runpy.run_path(str(Path(__file__).resolve().parent / "installation-manifest.py"))


def run(*args):
    """Run one installation step and stop on failure without invoking a shell."""
    subprocess.run(list(map(str, args)), check=True)


def runtime_module_processes(prefixes, proc_root=Path("/proc")):
    """Return exact managed module processes, without matching shell command text."""
    modules = {prefix.encode() + name.encode() for prefix in prefixes for name in (
        "merged_gamepad", "controller_router", "game_registry", "console_monitor", "receiver",
        "vision_app", "profile_control",
    )}
    found = []
    try:
        processes = proc_root.iterdir()
    except OSError:
        return found
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            arguments = (process / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        for index, argument in enumerate(arguments[:-1]):
            if argument == b"-m" and arguments[index + 1] in modules:
                found.append(int(process.name))
                break
    return sorted(found)


def retired_runtime_processes(proc_root=Path("/proc")):
    """Return only known pre-0.5.0 module processes."""
    return runtime_module_processes(["power" + "glove_vision."], proc_root)


def managed_runtime_processes(proc_root=Path("/proc")):
    """Return current and retired managed runtime processes."""
    return runtime_module_processes(
        ["virtualglove.", "power" + "glove_vision."], proc_root)


def write_file(path, content, mode=0o644, preserve=False):
    """Back up changed managed files; never overwrite a symlink or preserved setting."""
    path = Path(path)
    if any(parent.is_symlink() for parent in [path] + list(path.parents)):
        raise ValueError("Refusing symlink: " + str(path))
    if path.exists() and preserve:
        return
    data = content.encode() if isinstance(content, str) else content
    if path.exists():
        if path.read_bytes() == data and path.stat().st_mode & 0o777 == mode:
            return
        backup = BACKUPS / str(path).lstrip("/")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(backup))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".setup-tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Remove stale installer temporary file: " + str(temporary))
    with temporary.open("xb") as stream:
        stream.write(data)
    temporary.chmod(mode)
    if path.exists() and os.geteuid() == 0:
        owner = path.stat()
        os.chown(str(temporary), owner.st_uid, owner.st_gid)
    os.replace(str(temporary), str(path))


def backup_file(path):
    """Make one recovery copy before a runtime helper updates a managed setting."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return
    backup = BACKUPS / str(path).lstrip("/")
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(backup))


def hook_content(text, action):
    """Add an early, failure-safe shell hook once; preserve all existing commands."""
    executable = "/opt/virtualglove-src/retropie/runcommand-on" + action + "-virtualglove.sh"
    if any(executable in line and not line.lstrip().startswith("#") for line in text.splitlines()):
        return text
    if text.startswith("#!") and not re.match(r"^#!.*(?:/| )(?:ba|da)?sh(?:\s|$)", text.splitlines()[0]):
        raise ValueError("Existing runcommand hook is not a supported shell script")
    command = executable + (' "$1" "$2" "$3" "$4"' if action == "start" else "")
    block = "# VirtualGlove managed launch hook\n" + command + " || true\n"
    if text.startswith("#!"):
        first, _, rest = text.partition("\n")
        return first + "\n" + block + rest
    return "#!/bin/sh\n" + block + text


def valid_host(value):
    """Accept a simple DNS hostname or IPv4 address, not shell syntax or URLs."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", value):
        raise argparse.ArgumentTypeError("Use a hostname or IPv4 address")
    return value


def retired_buster_sources(entries):
    """Identify only obsolete Raspbian Buster hosts; Raspberry Pi's archive is separate."""
    obsolete = []
    for path, text in entries:
        if (re.search(r"(?im)^\s*deb(?:-src)?\s+[^\n#]*raspbian\.raspberrypi\.org/raspbian[^\n#]*\bbuster\b", text)
                or re.search(r"(?ims)^URIs:\s*https?://raspbian\.raspberrypi\.org/raspbian\s*$.*?^Suites:\s*[^\n]*\bbuster\b", text)):
            obsolete.append(str(path))
    return obsolete


def check_retropie_package_sources():
    """Fail before apt changes when an EOL Buster source has moved to the legacy host."""
    paths = [Path("/etc/apt/sources.list")]
    directory = Path("/etc/apt/sources.list.d")
    if directory.is_dir():
        paths.extend(sorted(directory.glob("*.list")))
        paths.extend(sorted(directory.glob("*.sources")))
    entries = [(path, path.read_text(errors="replace")) for path in paths
               if path.is_file() and not path.is_symlink()]
    obsolete = retired_buster_sources(entries)
    if obsolete:
        raise ValueError(
            "Raspberry Pi OS Buster's Raspbian repository moved to legacy.raspbian.org. "
            "Back up and update only raspbian.raspberrypi.org/raspbian in "
            + ", ".join(obsolete)
            + "; do not change archive.raspberrypi.org. Then run sudo apt-get update and retry. "
              "See docs/INSTALL_README.md or docs/TROUBLESHOOTING.md.")


def install_retropie(peer):
    """Install the system-Python receiver and preserve cabinet-specific configuration."""
    base = Path("/opt/retropie/configs/all")
    if not base.is_dir():
        raise ValueError("RetroPie configuration directory is missing")
    # Detect an unusable package source before creating the renamed config tree
    # or touching any other VirtualGlove-managed file.
    check_retropie_package_sources()
    # Preflight hook compatibility before migrating configuration, installing
    # packages, or changing any VirtualGlove-managed file.
    hooks = []
    for action in ("start", "end"):
        path = base / ("runcommand-on" + action + ".sh")
        if path.is_symlink():
            raise ValueError("Refusing symlink: " + str(path))
        text = path.read_text() if path.exists() else ""
        hooks.append((path, hook_content(text, action)))
    launcher = Path("/etc/virtualglove/launcher.json")
    if launcher.exists():
        current = json.loads(launcher.read_text())
        if peer and current.get("uno_q") != peer:
            print("ACTION  Existing launcher destination preserved; edit launcher.json if changing machines.")
    if not launcher.exists() and not peer:
        raise ValueError("First installation requires --peer YOUR-UNO-Q.local")
    run("apt-get", "update")
    run("apt-get", "install", "-y", "python3", "python3-evdev", "openssl", "avahi-daemon", "libnss-mdns")
    run("systemctl", "enable", "--now", "avahi-daemon")
    run("modprobe", "uinput")
    write_file("/etc/modules-load.d/virtualglove.conf", "uinput\n")
    destination = Path("/opt/virtualglove-src")
    if SOURCE.resolve() != destination.resolve():
        names = [str(path.relative_to(SOURCE))
                 for directory in ("src", "retropie", "config", "scripts", "native", "licenses")
                 for path in (SOURCE / directory).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
        names += [name for name in ("install-release.json", "LICENSE", "THIRD_PARTY_NOTICES.md")
                  if (SOURCE / name).is_file()]
        installation_manifest()["apply"](SOURCE, destination, BACKUPS / "application-payload", names)
    for source in (SOURCE / "retropie/bin").iterdir():
        write_file(Path("/opt/virtualglove/bin") / source.name, source.read_bytes(), 0o755)
    write_file("/usr/local/bin/virtualglove-controller-router",
               "#!/bin/sh\nexec /opt/virtualglove/bin/virtualglove-controller-router \"$@\"\n",
               0o755)
    for action in ("start", "end"):
        (destination / ("retropie/runcommand-on" + action + "-virtualglove.sh")).chmod(0o755)
    write_file("/etc/virtualglove/games.json", (SOURCE / "config/games.json").read_bytes(), preserve=True)
    config = json.loads((SOURCE / "config/launcher.example.json").read_text())
    config["uno_q"] = peer
    config["controller_router"] = controller_router_settings("retropie")
    if launcher.exists():
        existing = json.loads(launcher.read_text())
        existing["controller_router"] = config["controller_router"]
        config = existing
    write_file(launcher, json.dumps(config, indent=2) + "\n")
    # Never truncate an existing token. Empty means pairing is still required.
    token = Path("/etc/virtualglove/token")
    write_file(token, b"", 0o640, preserve=True)
    token.chmod(0o640)
    os.chown(str(token), 0, grp.getgrnam("input").gr_gid)
    for unit in ("virtualglove-receiver.service", "virtualglove-receiver.timer", "virtualglove-games.service",
                 "virtualglove-controller-router.service"):
        write_file(Path("/etc/systemd/system") / unit, (SOURCE / "retropie" / unit).read_bytes())
    profile = "VirtualGlove.cfg"
    write_file(base / "retroarch/autoconfig" / profile,
               (SOURCE / "retropie/retroarch" / profile).read_bytes(), preserve=True)
    for player in range(1, 5):
        profile = "VirtualGlove Merged Player %d.cfg" % player
        write_file(base / "retroarch/autoconfig/udev" / profile,
                   (SOURCE / "retropie/retroarch" / profile).read_bytes())
    for path, content in hooks:
        write_file(path, content, 0o755)
        path.chmod(path.stat().st_mode | 0o111)
    registry_directory = Path(json.loads(launcher.read_text()).get("registry", "/etc/virtualglove/games.json")).resolve().parent
    # systemd quoted strings preserve spaces and avoid percent specifier expansion.
    writable = str(registry_directory).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    write_file("/etc/systemd/system/virtualglove-games.service.d/registry.conf",
               '[Service]\nReadWritePaths=\nReadWritePaths="' + writable + '"\n')
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "virtualglove-games.service")
    run("systemctl", "restart", "virtualglove-games.service")
    router_config = Path("/etc/virtualglove/controller-router.json")
    if router_config.is_file():
        run("systemctl", "enable", "--now", "virtualglove-controller-router.service")
        run("systemctl", "restart", "virtualglove-controller-router.service")
    run("systemctl", "disable", "virtualglove-receiver.service")
    if len(token.read_text().strip()) >= 16:
        run("systemctl", "restart", "virtualglove-receiver.service")
    run("systemctl", "enable", "--now", "virtualglove-receiver.timer")


def install_wifi_status():
    """Install the same unprivileged Wi-Fi sampler during setup and application updates."""
    if str(SOURCE) != UNOQ_APP:
        raise ValueError("Wi-Fi sampler requires the standard App Lab installation path")
    write_file("/usr/local/libexec/virtualglove-wifi-status",
               (SOURCE / "uno-q/virtualglove-wifi-status.py").read_bytes(), 0o755)
    for suffix in ("service", "timer"):
        name = "virtualglove-wifi-status." + suffix
        write_file(Path("/etc/systemd/system") / name, (SOURCE / "uno-q" / name).read_bytes())
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "virtualglove-wifi-status.timer")
    run("systemctl", "start", "virtualglove-wifi-status.service")


def retire_unoq_legacy_runtime_names():
    """Disable and remove the exact host helpers shipped before VirtualGlove 0.5."""
    system_units = (
        "powerglove-system-shutdown.path",
        "powerglove-camera-recovery.path",
        "powerglove-wifi-status.timer",
    )
    service_units = (
        "powerglove-system-shutdown.service",
        "powerglove-camera-recovery.service",
        "powerglove-wifi-status.service",
    )
    unit_directory = Path("/etc/systemd/system")
    for name in system_units:
        path = unit_directory / name
        if path.exists() or path.is_symlink():
            run("systemctl", "disable", "--now", name)
    for name in service_units:
        path = unit_directory / name
        if path.exists() or path.is_symlink():
            run("systemctl", "stop", name)

    for path in [unit_directory / name for name in system_units + service_units] + [
        Path("/etc/tmpfiles.d/powerglove-system-shutdown.conf"),
        Path("/etc/tmpfiles.d/powerglove-camera-recovery.conf"),
        Path("/usr/local/libexec/powerglove-camera-recovery"),
        Path("/usr/local/libexec/powerglove-wifi-status"),
    ]:
        if path.exists() or path.is_symlink():
            path.unlink()

    user = pwd.getpwnam("arduino")
    home = Path(user.pw_dir)
    old_user_unit = home / ".config/systemd/user/powerglove-early-start.service"
    if old_user_unit.exists() or old_user_unit.is_symlink():
        run(*user_systemctl("disable", "--now", "powerglove-early-start.service"))
        old_user_unit.unlink()
    old_user_helper = home / ".local/lib/powerglove/uno-q-early-start.py"
    if old_user_helper.exists() or old_user_helper.is_symlink():
        old_user_helper.unlink()
    old_user_directory = old_user_helper.parent
    if old_user_directory.is_dir() and not any(old_user_directory.iterdir()):
        old_user_directory.rmdir()

    run("systemctl", "daemon-reload")
    run(*user_systemctl("daemon-reload"))


def install_unoq_runtime_names():
    """Install the current UNO Q host helpers."""
    app = SOURCE
    if str(app) != UNOQ_APP:
        raise ValueError("UNO Q setup currently requires App Lab path " + UNOQ_APP)
    # A PathExists unit acts immediately when it is enabled. Refuse to migrate
    # while an old shutdown request is pending, otherwise enabling the renamed
    # watcher can halt the board halfway through setup.
    if (app / "data/shutdown-request").exists():
        raise ValueError(
            "A pending shutdown request exists; remove it deliberately before "
            "migrating UNO Q runtime names"
        )
    for suffix, directory in (("path", "/etc/systemd/system"), ("service", "/etc/systemd/system"), ("conf", "/etc/tmpfiles.d")):
        name = "virtualglove-system-shutdown." + suffix
        write_file(Path(directory) / name, (app / "uno-q" / name).read_bytes())
    for suffix, directory in (("path", "/etc/systemd/system"), ("service", "/etc/systemd/system"), ("conf", "/etc/tmpfiles.d")):
        name = "virtualglove-camera-recovery." + suffix
        write_file(Path(directory) / name, (app / "uno-q" / name).read_bytes())
    write_file(
        "/usr/local/libexec/virtualglove-camera-recovery",
        (app / "uno-q/virtualglove-camera-recovery.py").read_bytes(),
        0o755,
    )
    run("/usr/local/libexec/virtualglove-camera-recovery", "--configure-if-present")
    run("systemctl", "daemon-reload")
    run("systemd-tmpfiles", "--create", "/etc/tmpfiles.d/virtualglove-system-shutdown.conf")
    run("systemd-tmpfiles", "--create", "/etc/tmpfiles.d/virtualglove-camera-recovery.conf")
    run("systemctl", "enable", "--now", "virtualglove-system-shutdown.path")
    run("systemctl", "enable", "--now", "virtualglove-camera-recovery.path")
    install_early_start()
    install_wifi_status()
    retire_unoq_legacy_runtime_names()


def install_unoq(peer):
    """Complete the CLI-started app with networking, shutdown and early startup."""
    app = SOURCE
    if str(app) != UNOQ_APP:
        raise ValueError("UNO Q setup currently requires App Lab path " + UNOQ_APP)
    compose = app / ".cache/app-compose.yaml"
    if not compose.exists():
        raise ValueError("Start the app with install-uno-q.sh before completing host setup")
    if (app / "data/shutdown-request").exists():
        raise ValueError("A pending shutdown request exists; remove it deliberately before setup")
    controller_name = socket.gethostname().split(".", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", controller_name):
        raise ValueError("The UNO Q hostname is not safe for the Controller website")
    identity = app / "data/controller-hostname"
    write_file(identity, controller_name + "\n")
    user = pwd.getpwnam("arduino")
    os.chown(str(identity), user.pw_uid, user.pw_gid)
    run("apt-get", "update")
    run("apt-get", "install", "-y", "avahi-daemon", "libnss-mdns", "uhubctl")
    run("python3", str(app / "scripts/configure-uno-q-avahi.py"))
    run("systemctl", "enable", "--now", "avahi-daemon")
    run("systemctl", "restart", "avahi-daemon")
    install_unoq_runtime_names()
    # Use the same idempotent Compose transformation as Wi-Fi deployment.
    import runpy
    configure = runpy.run_path(str(app / "scripts/configure-uno-q-mdns.py"))["configure"]
    original = compose.read_bytes()
    backup = BACKUPS / "uno-q-app-compose.yaml"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    configure(compose)
    text = compose.read_text()
    if "- 8443:8443" not in text:
        if "- 8088:8088" not in text:
            raise ValueError("Expected app port 8088 in Compose configuration")
        compose.write_text(text.replace("- 8088:8088", "- 8088:8088\n    - 8443:8443", 1))
    user = pwd.getpwnam("arduino")
    os.chown(str(compose), user.pw_uid, user.pw_gid)
    # App Lab properties belong to the non-root desktop account.
    run("runuser", "-u", "arduino", "--", "arduino-app-cli", "properties", "set", "default", app)
    # App Lab's generated Compose file expands brick bind mounts from APP_HOME.
    # setup-machine runs under sudo, outside the App Lab CLI environment, so pass
    # it explicitly or Compose resolves those mounts from filesystem root.
    run("env", "APP_HOME=" + str(app), "docker", "compose", "-f", compose,
        "up", "-d", "--force-recreate")
    if peer:
        print("Receiver setting is preserved; choose " + peer + " on the Connection page if needed.")


def user_systemctl(*args):
    """Address the Arduino user manager consistently from a sudo installation."""
    user = pwd.getpwnam("arduino")
    prefix = ["runuser", "-u", "arduino", "--"] if os.geteuid() != user.pw_uid else []
    return prefix + ["env", "XDG_RUNTIME_DIR=/run/user/" + str(user.pw_uid),
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/" + str(user.pw_uid) + "/bus",
            "systemctl", "--user"] + list(args)


def install_early_start():
    """Install the guarded helper and enable it for subsequent boots without an SWD write now."""
    user = pwd.getpwnam("arduino")
    home = Path(user.pw_dir)
    for source, relative in (("scripts/uno-q-early-start.py", ".local/lib/virtualglove/uno-q-early-start.py"),
                             ("uno-q/virtualglove-early-start.service", ".config/systemd/user/virtualglove-early-start.service")):
        target = home / relative
        if any(parent.is_symlink() for parent in [target] + list(target.parents)):
            raise ValueError("Refusing symbolic helper path: " + str(target))
        write_file(target, (SOURCE / source).read_bytes())
        os.chown(str(target), user.pw_uid, user.pw_gid)
        for parent in target.parents:
            if parent == home:
                break
            os.chown(str(parent), user.pw_uid, user.pw_gid)
    run("loginctl", "enable-linger", "arduino")
    run("systemctl", "start", "user@%s.service" % user.pw_uid)
    run(*user_systemctl("daemon-reload"))
    trial = home / ".config/systemd/user/virtualglove-early-start-trial.service"
    if trial.exists():
        run(*user_systemctl("disable", "virtualglove-early-start-trial.service"))
    run(*user_systemctl("enable", "virtualglove-early-start.service"))
    run(*user_systemctl("reset-failed", "virtualglove-early-start.service"))
    print("PASS  Early-start helper installed for the next boot; existing sketch animation preserved.")


def wait_unoq():
    """Require the app and exact release firmware after a cold startup."""
    last = "Controller did not answer"
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8088/status", timeout=2) as response:
                status = json.load(response)
            state = status.get("firmware", {}).get("state")
            if state == "matched":
                return
            last = "Matrix firmware status is " + str(state or "unavailable")
        except (OSError, ValueError, AttributeError) as error:
            last = str(error)
        if _ < 89:
            time.sleep(2)
    raise ValueError("Controller startup validation failed: " + last)


def registered_roms():
    """Find registered NES games in standard RetroPie account ROM directories."""
    config = json.loads(Path("/etc/virtualglove/launcher.json").read_text())
    registry = json.loads(Path(config.get("registry", "/etc/virtualglove/games.json")).read_text())["games"]
    results = []
    for home in Path("/home").iterdir():
        directory = home / "RetroPie/roms/nes"
        if directory.is_dir():
            for rom in directory.rglob("*"):
                if rom.is_file() and rom.name in registry:
                    results.append((rom, registry[rom.name]))
    return results


def configure_games(confirm):
    """Prepare FCEUmm games and offer the optional source-built native core."""
    prefix = Path("/opt/retropie")
    core = prefix / "libretrocores/lr-fceumm/fceumm_libretro.so"
    retroarch = prefix / "emulators/retroarch/bin/retroarch"
    if not core.is_file() or not retroarch.is_file():
        user = os.environ.get("SUDO_USER", "")
        home = Path(pwd.getpwnam(user).pw_dir) if user else Path("/root")
        script = home / "RetroPie-Setup/retropie_packages.sh"
        if script.is_file() and confirm("Install missing RetroArch/FCEUmm using RetroPie Setup? This may take several minutes"):
            for package, artifact in (("retroarch", retroarch), ("lr-fceumm", core)):
                if not artifact.is_file():
                    run("bash", script, package, "install_bin")
                    run("bash", script, package, "configure")
        else:
            print("ACTION  Install lr-fceumm using RetroPie Setup, then rerun this installer.")
    import runpy
    roms = registered_roms()
    super_glove_ball_roms = [rom for rom, profile in roms if profile == "super_glove_ball"]
    native = prefix / "libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so"
    if super_glove_ball_roms and not native.is_file():
        prompt = ("Build and register optional lr-nestopia-powerglove for Super Glove Ball? "
                  "This installs build tools and downloads pinned GPLv2 source")
        if confirm(prompt):
            run("apt-get", "install", "-y", "git", "build-essential")
            with tempfile.TemporaryDirectory(prefix="powerglove-nestopia-", dir="/var/tmp") as build:
                run("bash", SOURCE / "scripts/install-nestopia-powerglove.sh", build)
    if super_glove_ball_roms and native.is_file():
        selector = runpy.run_path(str(SOURCE / "scripts/configure-super-glove-ball-core.py"))
        system_path, system_text, option_path, option_text = selector["native_registration"](prefix)
        write_file(system_path, system_text)
        write_file(option_path, option_text)
        print("PASS  Both Super Glove Ball emulators are available; FCEUmm remains selected until you choose native mode.")
    elif super_glove_ball_roms:
        print("INFO  Super Glove Ball will use FCEUmm; the optional native core was not installed.")

    dot = prefix / "libretrocores/lr-powerglove-dot/powerglove_dot_libretro.so"
    install_dot = dot.is_file()
    if not install_dot:
        install_dot = confirm(
            "Install the optional VirtualGlove Calibration Test in RetroPie's Ports menu? "
            "It needs no ROM and displays native hand position as a dot"
        )
        if install_dot:
            run("apt-get", "install", "-y", "build-essential")
    if install_dot:
        run("bash", SOURCE / "scripts/install-powerglove-dot.sh", prefix)
        option = prefix / "configs/nes/powerglove-native.cfg"
        write_file(option, 'input_libretro_device_p1 = "517"\nvideo_threaded = "false"\n')
        user_name = os.environ.get("SUDO_USER", "")
        if user_name:
            account = pwd.getpwnam(user_name)
            port = Path(account.pw_dir) / "RetroPie/roms/ports/VirtualGlove Calibration Test.sh"
            write_file(port, '#!/bin/sh\nexec /opt/virtualglove/bin/virtualglove-dot\n', 0o755)
            os.chown(str(port), account.pw_uid, account.pw_gid)
            print("PASS  VirtualGlove Calibration Test is available in Ports.")
        else:
            print("ACTION  Add /opt/virtualglove/bin/virtualglove-dot to the intended user's Ports menu.")

    zap = runpy.run_path(str(SOURCE / "scripts/configure-bsb-zap.py"))
    for rom, profile in roms:
        if profile != "bad_street_brawler":
            continue
        try:
            configs = prefix / "configs"
            games_path = configs / "all/emulators.cfg"
            system = zap["settings"](configs / "nes/emulators.cfg")
            games = zap["settings"](games_path)
            import hashlib
            key = "a" + hashlib.md5(("nes" + str(rom) + "\n").encode()).hexdigest()
            modern = re.sub(r"[^a-zA-Z0-9_-]", "", "nes_" + rom.stem)
            selected = games.get(key) or games.get(modern) or system.get("default")
            if selected != "lr-fceumm" and core.is_file() and "lr-fceumm" in system:
                if confirm("Use FCEUmm for " + rom.name + " so Glove Zap is supported?"):
                    text = games_path.read_text() if games_path.exists() else ""
                    text = "\n".join(line for line in text.splitlines() if not re.match(r"^\s*" + re.escape(key) + r"\s*=", line))
                    write_file(games_path, text + "\n" + key + ' = "lr-fceumm"\n')
            result = zap["main"](["--rom", str(rom), "--apply"])
            if result:
                print("ACTION  Finish Glove Zap setup for " + rom.name + "; rerun after resolving the message above.")
        except (ValueError, OSError) as error:
            print("ACTION  " + str(error))


def recalbox_custom_hook(text):
    """Add the persistent service hook without replacing user startup commands."""
    command = 'sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service "$1"'
    if any(command in line and not line.lstrip().startswith("#")
           for line in text.splitlines()):
        return text
    block = "# VirtualGlove managed service hook\n" + command + " || true\n"
    if text.startswith("#!"):
        first, _, rest = text.partition("\n")
        return first + "\n" + block + rest
    return "#!/bin/sh\n" + block + text


def merged_controller_module():
    """Load the shared dependency-free merged-controller implementation."""
    if str(SOURCE / "src") not in sys.path:
        sys.path.insert(0, str(SOURCE / "src"))
    from virtualglove import merged_gamepad
    return merged_gamepad


def controller_router_module():
    """Load the shared Player 1-4 Controller Router implementation."""
    if str(SOURCE / "src") not in sys.path:
        sys.path.insert(0, str(SOURCE / "src"))
    from virtualglove import controller_router
    return controller_router


def merged_controller_paths(platform):
    """Return the platform's frontend map and saved Player 1 record paths."""
    if platform == "recalbox":
        return (Path("/recalbox/share/system/.emulationstation/es_input.cfg"),
                Path("/recalbox/share/system/virtualglove/data/player1-controller.json"))
    return (Path("/userdata/system/configs/emulationstation/es_input.cfg"),
            Path("/userdata/system/virtualglove/data/player1-controller.json"))


def list_player1_devices(platform):
    """Print stable configured-gamepad identifiers for unattended installation."""
    merged = merged_controller_module()
    es_inputs, _config = merged_controller_paths(platform)
    candidates = merged.controller_candidates(es_inputs)
    if not candidates:
        raise ValueError("no connected configured gamepads were found")
    for item in candidates:
        print(item["id"] + "  " + item["name"])


def configure_merged_player1(platform, requested=None):
    """Preserve or explicitly select the physical source for merged Player 1."""
    merged = merged_controller_module()
    es_inputs, config = merged_controller_paths(platform)
    if config.is_file() and requested is None:
        saved = merged.load_controller(config)
        if saved["platform"] != platform:
            raise ValueError(
                "saved Player 1 controller belongs to " + saved["platform"] +
                "; select this console's controller with --player1-device")
        connected = merged.find_saved_controller(
            saved, merged.controller_candidates(es_inputs))
        if connected is not None and connected["mapping"] != saved["mapping"]:
            saved["mapping"] = connected["mapping"]
            write_file(config, json.dumps(saved, indent=2) + "\n")
        selected = saved
        router = controller_router_module()
        router.migrate_player1(config, config.with_name(router.CONFIG_NAME), platform)
        return selected
    candidate = merged.choose_controller(
        merged.controller_candidates(es_inputs), requested=requested)
    data = {"format": merged.FORMAT, "platform": platform,
            **{key: candidate.get(key, "") for key in
               ("id", "name", "guid", "vendor", "product", "version", "uniq", "phys")},
            "mapping": candidate["mapping"]}
    write_file(config, json.dumps(data, indent=2) + "\n")
    router = controller_router_module()
    router_path = config.with_name(router.CONFIG_NAME)
    if requested is not None or not router_path.exists():
        routed = router.validate_config({
            "format": router.FORMAT, "platform": platform,
            "players": [{"player": 1, "sources": [data]}],
            "virtualglove_player": 1,
            "physical_scope": "all",
        })
        write_file(router_path, json.dumps(routed, indent=2) + "\n")
    return data


def controller_router_settings(platform):
    """Return trusted console-local paths exposed through the paired inputs API."""
    if platform == "recalbox":
        root = Path("/recalbox/share/system/virtualglove")
        return {"path": str(root / "data/controller-router.json"), "platform": platform,
                "es_inputs": "/recalbox/share/system/.emulationstation/es_input.cfg",
                "retroarch_config": "/recalbox/share/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg"}
    if platform == "batocera":
        root = Path("/userdata/system/virtualglove")
        return {"path": str(root / "data/controller-router.json"), "platform": platform,
                "es_inputs": "/userdata/system/configs/emulationstation/es_input.cfg",
                "retroarch_config": "/userdata/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg"}
    return {"path": "/etc/virtualglove/controller-router.json", "platform": "retropie",
            "es_inputs": "/opt/retropie/configs/all/emulationstation/es_input.cfg",
            "retroarch_config": "/opt/retropie/configs/all/retroarch/config/FCEUmm/FCEUmm.cfg"}


def install_recalbox(peer, player1_device=None):
    """Install into Recalbox's persistent share without modifying its read-only OS."""
    version_file = Path("/recalbox/recalbox.version")
    if not version_file.is_file():
        raise ValueError("This target is not Recalbox")
    version = version_file.read_text().strip()
    if not re.fullmatch(r"10(?:\.[0-9]+)+", version):
        raise ValueError("Recalbox 10.x is required; found " + version)
    if subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError("Close the running game before installing VirtualGlove")
    if not Path("/dev/uinput").exists() or not Path("/usr/lib/libretro/fceumm_libretro.so").is_file():
        raise ValueError("Recalbox uinput and FCEUmm are required")

    destination = Path("/recalbox/share/system/virtualglove")
    architecture = Path("/recalbox/recalbox.arch").read_text().strip()
    native_manifest = SOURCE / "native/recalbox/manifest.json"
    native_names = [str(path.relative_to(SOURCE))
                    for path in (SOURCE / "native/nestopia-powerglove").rglob("*")
                    if path.is_file()]
    if native_manifest.is_file():
        native_names.append(str(native_manifest.relative_to(SOURCE)))
        native_data = json.loads(native_manifest.read_text())
        verifier = SOURCE / "scripts/verify-recalbox-native-core.py"
        resolved = subprocess.run(
            ["python3", str(verifier), "--manifest", str(native_manifest),
             "--arch", architecture, "--version", version, "--resolve-core"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True)
        if resolved.returncode == 0 and resolved.stdout.strip():
            candidate = Path(resolved.stdout.strip())
            selected_version = candidate.parent.name
            native_entry = native_data["cores"][architecture][selected_version]
            subprocess.run(["python3", str(verifier), "--manifest", str(native_manifest),
                            "--core", str(candidate), "--arch", architecture,
                            "--version", version, "--load"],
                           check=True)
            native_names.append(str(candidate.relative_to(SOURCE)))
            source_archive = native_manifest.parent / native_entry["source_file"]
            native_names.append(str(source_archive.relative_to(SOURCE)))
        else:
            print("ACTION  No compatible native Super Glove Ball core is packaged for Recalbox " +
                  version + " target " + architecture + "; FCEUmm remains available.")
    names = [str(path.relative_to(SOURCE))
             for directory in ("src", "recalbox", "config", "scripts", "python")
             for path in (SOURCE / directory).rglob("*")
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    names += native_names
    names += [name for name in ("install-release.json", "LICENSE", "THIRD_PARTY_NOTICES.md")
              if (SOURCE / name).is_file()]
    if SOURCE.resolve() != destination.resolve():
        installation_manifest()["apply"](
            SOURCE, destination, BACKUPS / "application-payload", names)
    data = destination / "data"
    data.mkdir(parents=True, exist_ok=True)
    write_file(data / "games.json", (SOURCE / "config/games.json").read_bytes(), preserve=True)
    launcher = data / "launcher.json"
    settings = json.loads((SOURCE / "config/launcher.example.json").read_text())
    settings.update({
        "uno_q": peer,
        "token_file": str(data / "token"),
        "registry": str(data / "games.json"),
        "controller_router": controller_router_settings("recalbox"),
    })
    if launcher.exists():
        existing = json.loads(launcher.read_text())
        existing["controller_router"] = settings["controller_router"]
        settings = existing
    write_file(launcher, json.dumps(settings, indent=2) + "\n")
    write_file(data / "token", b"", preserve=True)
    configure_merged_player1("recalbox", player1_device)

    service = destination / "recalbox/virtualglove-service"
    write_file(destination / "scripts/virtualglove-controller-router",
               (SOURCE / "scripts/virtualglove-controller-router").read_bytes(), 0o755)
    custom = Path("/recalbox/share/system/custom.sh")
    write_file(custom, recalbox_custom_hook(
        custom.read_text() if custom.exists() else ""), 0o755)
    custom.chmod(0o755)
    backup_file("/recalbox/share/system/configs/retroarch/nes.cfg")
    backup_file("/recalbox/share/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg")
    backup_file("/recalbox/share/system/configs/retroarch/config/Nestopia/Nestopia.cfg")
    run("sh", service, "restart")


def check_recalbox(report):
    """Check only persistent Recalbox integration and active processes."""
    root = Path("/recalbox/share/system/virtualglove")
    report.check("No retired VirtualGlove processes", not retired_runtime_processes())
    report.check("Recalbox 10.x detected", Path("/recalbox/recalbox.version").is_file() and
                 Path("/recalbox/recalbox.version").read_text().strip().startswith("10."))
    report.check("Persistent VirtualGlove installation", (root / "src/virtualglove/receiver.py").is_file())
    report.check("Kernel virtual-input support", Path("/dev/uinput").exists())
    report.check("FCEUmm core installed", Path("/usr/lib/libretro/fceumm_libretro.so").is_file())
    report.check("Stock Nestopia core installed",
                 Path("/usr/lib/libretro/nestopia_libretro.so").is_file(), pending=True)
    controller = root / "data/player1-controller.json"
    try:
        merged = merged_controller_module()
        selected = merged.load_controller(controller)
        report.check("Physical Player 1 selected", bool(selected.get("name")))
        report.check("Physical Player 1 connected", merged.find_saved_controller(
            selected, merged.input_devices()) is not None, pending=True)
        index = merged.merged_joypad_index()
        report.check("Merged Player 1 gamepad available", index is not None)
        for core in ("FCEUmm", "Nestopia"):
            nes_text = Path(
                "/recalbox/share/system/configs/retroarch/config/%s/%s.cfg" %
                (core, core)).read_text()
            report.check("%s uses merged Player 1" % core, index is not None and
                         ('input_player1_joypad_index = "%d"' % index) in nes_text)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        report.check("Merged Player 1 configuration", False)
    try:
        router = controller_router_module()
        routed = router.load_config(root / "data/controller-router.json")
        players = router.enabled_players(routed)
        indexes = router.output_indexes(players)
        report.check("Controller Router configuration", routed["platform"] == "recalbox")
        report.check("Controller Router outputs available", len(indexes) == len(players))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        report.check("Controller Router configuration", False)
    native_manifest = root / "native/recalbox/manifest.json"
    native = None
    if native_manifest.is_file():
        resolved = subprocess.run(
            ["python3", str(root / "scripts/verify-recalbox-native-core.py"),
             "--manifest", str(native_manifest), "--arch",
             Path("/recalbox/recalbox.arch").read_text().strip(), "--version",
             Path("/recalbox/recalbox.version").read_text().strip(), "--resolve-core"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True)
        if resolved.returncode == 0 and resolved.stdout.strip():
            native = Path(resolved.stdout.strip())
    report.check("Optional Nestopia (VirtualGlove) core",
                 bool(native and native.is_file()), pending=not (native and native.is_file()))
    report.check("Boot hook installed", "virtualglove-service" in
                 (Path("/recalbox/share/system/custom.sh").read_text()
                  if Path("/recalbox/share/system/custom.sh").is_file() else ""))
    service = root / "recalbox/virtualglove-service"
    token = root / "data/token"
    if service.is_file():
        paired = token.is_file() and len(token.read_text().strip()) >= 16
        for process in ("game_registry", "console_monitor"):
            report.check("Process running: " + process,
                         subprocess.run(["sh", service, "status"], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL).stdout.decode().find(
                                            "RUNNING " + process) >= 0,
                         pending=not paired)
        status = subprocess.run(["sh", service, "status"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL).stdout.decode()
        report.check("Process running: receiver", "RUNNING receiver" in status,
                     pending=not paired)
    else:
        report.check("Recalbox VirtualGlove processes", False)
    report.check("Complete authenticated pairing", token.is_file() and
                 len(token.read_text().strip()) >= 16, pending=True)


def batocera_version():
    """Return Batocera's leading numeric release or zero when unavailable."""
    try:
        match = re.search(r"\d+", Path("/usr/share/batocera/batocera.version").read_text())
        return int(match.group()) if match else 0
    except OSError:
        return 0


def install_batocera(peer, player1_device=None):
    """Install persistent Batocera service and game-event integrations."""
    version = batocera_version()
    if version < 38:
        raise ValueError("Batocera 38 or newer is required")
    if subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError("Close the running game before installing VirtualGlove")
    if not Path("/dev/uinput").exists() or not Path("/usr/lib/libretro/fceumm_libretro.so").is_file():
        raise ValueError("Batocera uinput and FCEUmm are required")

    destination = Path("/userdata/system/virtualglove")
    names = [str(path.relative_to(SOURCE))
             for directory in ("src", "recalbox", "batocera", "config", "scripts", "python",
                               "native/batocera", "native/nestopia-powerglove")
             for path in (SOURCE / directory).rglob("*")
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    names += [name for name in ("install-release.json", "LICENSE", "THIRD_PARTY_NOTICES.md")
              if (SOURCE / name).is_file()]
    if SOURCE.resolve() != destination.resolve():
        installation_manifest()["apply"](
            SOURCE, destination, BACKUPS / "application-payload", names)
    data = destination / "data"
    data.mkdir(parents=True, exist_ok=True)
    write_file(data / "games.json", (SOURCE / "config/games.json").read_bytes(), preserve=True)
    launcher = data / "launcher.json"
    settings = json.loads((SOURCE / "config/launcher.example.json").read_text())
    settings.update({"uno_q": peer, "token_file": str(data / "token"),
                     "registry": str(data / "games.json"),
                     "controller_router": controller_router_settings("batocera")})
    if launcher.exists():
        existing = json.loads(launcher.read_text())
        existing["controller_router"] = settings["controller_router"]
        settings = existing
    write_file(launcher, json.dumps(settings, indent=2) + "\n")
    write_file(data / "token", b"", preserve=True)
    configure_merged_player1("batocera", player1_device)

    service = Path("/userdata/system/services/VirtualGlove")
    event = Path("/userdata/system/scripts/virtualglove-game")
    write_file(service, (destination / "batocera/VirtualGlove").read_bytes(), 0o755)
    write_file(event, (destination / "batocera/virtualglove-game").read_bytes(), 0o755)
    executables = [
        service, event,
        destination / "batocera/virtualglove-core-mount",
        destination / "scripts/install-batocera-nestopia-powerglove.sh",
        destination / "scripts/configure-batocera-super-glove-ball-core.py",
        destination / "scripts/verify-batocera-native-core.py",
    ]
    write_file(destination / "scripts/virtualglove-controller-router",
               (SOURCE / "scripts/virtualglove-controller-router").read_bytes(), 0o755)
    executables.append(destination / "scripts/virtualglove-controller-router")
    for executable in executables:
        executable.chmod(0o755)
    backup_file("/userdata/system/configs/retroarch/nes.cfg")
    backup_file("/userdata/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg")
    backup_file("/userdata/system/configs/retroarch/config/Nestopia/Nestopia.cfg")
    run("batocera-services", "enable", "VirtualGlove")
    subprocess.run(["batocera-services", "stop", "VirtualGlove"], check=False)
    run("batocera-services", "start", "VirtualGlove")


def check_batocera(report):
    """Check persistent Batocera integration without inspecting private values."""
    root = Path("/userdata/system/virtualglove")
    report.check("No retired VirtualGlove processes", not retired_runtime_processes())
    report.check("Supported Batocera release", batocera_version() >= 38)
    report.check("Persistent VirtualGlove installation", (root / "src/virtualglove/receiver.py").is_file())
    report.check("Kernel virtual-input support", Path("/dev/uinput").exists())
    report.check("FCEUmm core installed", Path("/usr/lib/libretro/fceumm_libretro.so").is_file())
    report.check("Stock Nestopia core installed",
                 Path("/usr/lib/libretro/nestopia_libretro.so").is_file(), pending=True)
    report.check("Batocera service installed", Path("/userdata/system/services/VirtualGlove").is_file())
    report.check("Batocera game hook installed", Path("/userdata/system/scripts/virtualglove-game").is_file())
    controller = root / "data/player1-controller.json"
    try:
        merged = merged_controller_module()
        selected = merged.load_controller(controller)
        report.check("Physical Player 1 selected", bool(selected.get("name")))
        report.check("Physical Player 1 connected", merged.find_saved_controller(
            selected, merged.input_devices()) is not None, pending=True)
        index = merged.merged_joypad_index()
        report.check("Merged Player 1 gamepad available", index is not None)
        for core in ("FCEUmm", "Nestopia"):
            nes_text = Path(
                "/userdata/system/configs/retroarch/config/%s/%s.cfg" %
                (core, core)).read_text()
            report.check("%s uses merged Player 1" % core, index is not None and
                         ('input_player1_joypad_index = "%d"' % index) in nes_text)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        report.check("Merged Player 1 configuration", False)
    try:
        router = controller_router_module()
        routed = router.load_config(root / "data/controller-router.json")
        players = router.enabled_players(routed)
        indexes = router.output_indexes(players)
        report.check("Controller Router configuration", routed["platform"] == "batocera")
        report.check("Controller Router outputs available", len(indexes) == len(players))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        report.check("Controller Router configuration", False)
    native = Path("/usr/lib/libretro/nestopia_powerglove_libretro.so")
    native_info = Path("/usr/share/libretro/info/nestopia_powerglove_libretro.info")
    report.check("Optional native Super Glove Ball core", native.is_file() and
                 native_info.is_file(), pending=True)
    manifest = root / "native/batocera/manifest.json"
    resolved = None
    if manifest.is_file() and Path("/usr/share/batocera/batocera.arch").is_file():
        result = subprocess.run(
            ["python3", str(root / "scripts/verify-batocera-native-core.py"),
             "--manifest", str(manifest), "--arch",
             Path("/usr/share/batocera/batocera.arch").read_text().strip(), "--version",
             Path("/usr/share/batocera/batocera.version").read_text().strip(),
             "--resolve-core"], check=False, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0 and result.stdout.strip():
            resolved = Path(result.stdout.strip())
    report.check("Packaged native core matches this Batocera target",
                 bool(resolved and resolved.is_file()), pending=True)
    report.command("Batocera VirtualGlove service enabled",
                   ["batocera-services", "is-enabled", "VirtualGlove"])
    token = root / "data/token"
    report.check("Complete authenticated pairing", token.is_file() and
                 len(token.read_text().strip()) >= 16, pending=True)


class Report:
    """Collect explicit check results without printing private configuration values."""
    def __init__(self):
        self.failures = 0
        self.pending = 0

    def check(self, label, condition, pending=False):
        """Print one result and retain the final exit-code category."""
        if condition:
            print("PASS  " + label)
        elif pending:
            self.pending += 1
            print("ACTION  " + label)
        else:
            self.failures += 1
            print("FAIL  " + label)

    def command(self, label, args):
        """Check a command without displaying logs that may contain private data."""
        try:
            result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            self.check(label, result.returncode == 0)
        except (OSError, subprocess.TimeoutExpired):
            self.check(label, False)

    def release(self):
        """Display the installed package tag without reading private runtime settings."""
        path = SOURCE / "install-release.json"
        if path.is_file():
            try:
                print("Installed release: " + json.loads(path.read_text())["version"])
            except (ValueError, KeyError):
                self.check("Installed release identity is readable", False)

    def finish(self):
        """Distinguish technical failures from required human pairing/play verification."""
        self.release()
        print("Checks: %d failed, %d require action." % (self.failures, self.pending))
        return 1 if self.failures else 2 if self.pending else 0


def check_inventory(report, root):
    """Verify the installed payload rather than a temporary release staging tree."""
    issues = installation_manifest()["check"](root)
    if not issues:
        report.check("Installation manifest matches managed files", True)
    for issue in issues:
        report.check("Installation manifest: " + issue, False,
                     pending=issue.startswith(("Locally modified:", "No installation manifest;")))


def check_retropie(report):
    """Inspect boot configuration, receiver prerequisites and launch integration."""
    check_inventory(report, Path("/opt/virtualglove-src"))
    report.check("No retired VirtualGlove processes", not retired_runtime_processes())
    report.command("Avahi enabled at boot", ["systemctl", "is-enabled", "--quiet", "avahi-daemon"])
    report.command("Avahi running", ["systemctl", "is-active", "--quiet", "avahi-daemon"])
    report.command("mDNS hostname dependency installed", ["dpkg", "--verify", "libnss-mdns"])
    report.check("uinput device exists", Path("/dev/uinput").exists())
    report.command("Receiver Python dependency", ["python3", "-c", "import evdev"])
    report.command("Delayed boot timer enabled", ["systemctl", "is-enabled", "--quiet", "virtualglove-receiver.timer"])
    report.command("Delayed boot timer active", ["systemctl", "is-active", "--quiet", "virtualglove-receiver.timer"])
    token = Path("/etc/virtualglove/token")
    paired = token.exists() and 16 <= len(token.read_text().strip()) <= 256
    report.check("Local pairing token configured (pair on the Connection page if missing)", paired, pending=True)
    if paired:
        router = Path("/etc/virtualglove/controller-router.json")
        if router.is_file():
            report.command("Controller Router running", ["systemctl", "is-active", "--quiet",
                                                          "virtualglove-controller-router.service"])
            report.check("Controller Router receiver socket available",
                         Path("/run/virtualglove/controller-router.sock").is_socket())
        report.command("Receiver service running", ["systemctl", "is-active", "--quiet", "virtualglove-receiver.service"])
        report.command("Games service running", ["systemctl", "is-active", "--quiet", "virtualglove-games.service"])
    for action in ("start", "end"):
        path = Path("/opt/retropie/configs/all/runcommand-on" + action + ".sh")
        text = path.read_text() if path.exists() else ""
        report.check(action + " launch hook installed", "runcommand-on" + action + "-virtualglove.sh" in text)
    launcher = Path("/etc/virtualglove/launcher.json")
    try:
        config = json.loads(launcher.read_text())
        socket.getaddrinfo(config["uno_q"], 55356)
        report.check("Configured UNO Q hostname resolves", True)
    except (OSError, ValueError, KeyError):
        report.check("Configured UNO Q hostname resolves", False)
    report.check("RetroArch installed", Path("/opt/retropie/emulators/retroarch/bin/retroarch").is_file(), pending=True)
    report.check("FCEUmm installed for supported NES games", Path("/opt/retropie/libretrocores/lr-fceumm/fceumm_libretro.so").is_file(), pending=True)
    native = Path("/opt/retropie/libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so")
    if native.is_file():
        import runpy
        selector = runpy.run_path(str(SOURCE / "scripts/configure-super-glove-ball-core.py"))
        system = selector["settings"](Path("/opt/retropie/configs/nes/emulators.cfg"))
        option = Path("/opt/retropie/configs/nes/powerglove-native.cfg")
        report.check("Optional native Super Glove Ball core registered",
                     "lr-nestopia-powerglove" in system and option.is_file())
        report.check("Native core GPLv2 license installed", native.with_name("COPYING").is_file())
    dot = Path("/opt/retropie/libretrocores/lr-powerglove-dot/powerglove_dot_libretro.so")
    if dot.is_file():
        user_name = os.environ.get("SUDO_USER", "")
        account = pwd.getpwnam(user_name) if user_name else None
        launcher = (Path(account.pw_dir) / "RetroPie/roms/ports/VirtualGlove Calibration Test.sh"
                    if account else None)
        report.check("Optional VirtualGlove Calibration Test installed",
                     launcher is not None and launcher.is_file())
    try:
        roms = registered_roms()
        report.check("Registered ROMs found (supply your own games)", bool(roms), pending=True)
        import runpy
        zap = runpy.run_path(str(SOURCE / "scripts/configure-bsb-zap.py"))
        for rom, profile in roms:
            if profile == "bad_street_brawler":
                report.check("Glove Zap configured: " + rom.name,
                             zap["main"](["--rom", str(rom), "--check"]) == 0, pending=True)
    except (OSError, ValueError, KeyError):
        report.check("Game registry readable; review custom ROM paths if needed", False, pending=True)
    report.check("Confirm controls in a game; a local token alone does not prove pairing", False, pending=True)


def check_unoq(report):
    """Check boot persistence, the app-owned resolver and public application health."""
    check_inventory(report, Path(UNOQ_APP))
    report.check("No retired VirtualGlove processes", not retired_runtime_processes())
    report.command("Avahi enabled at boot", ["systemctl", "is-enabled", "--quiet", "avahi-daemon"])
    report.command("mDNS hostname dependency installed", ["dpkg", "--verify", "libnss-mdns"])
    report.command("Avahi running", ["systemctl", "is-active", "--quiet", "avahi-daemon"])
    identity = SOURCE / "data/controller-hostname"
    report.check("Container website uses the UNO Q hostname",
                 identity.is_file() and
                 identity.read_text().strip().lower() == socket.gethostname().split(".", 1)[0].lower())
    report.command("Shutdown helper enabled", ["systemctl", "is-enabled", "--quiet", "virtualglove-system-shutdown.path"])
    report.command("Shutdown helper running", ["systemctl", "is-active", "--quiet", "virtualglove-system-shutdown.path"])
    report.check("Shutdown readiness marker", (SOURCE / "data/.shutdown-enabled").exists())
    report.command("Wi-Fi sampler enabled", ["systemctl", "is-enabled", "--quiet", "virtualglove-wifi-status.timer"])
    report.command("Wi-Fi sampler running", ["systemctl", "is-active", "--quiet", "virtualglove-wifi-status.timer"])
    try:
        args = ["arduino-app-cli", "properties", "get", "default", "--format", "json"]
        if os.geteuid() == 0:
            args = ["runuser", "-u", "arduino", "--"] + args
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=True)
        report.check("VirtualGlove is the startup app", json.loads(result.stdout)["app"]["FullPath"] == str(SOURCE))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        report.check("VirtualGlove is the startup app", False)

    report.command("Arduino user starts at boot", ["test", "-f", "/var/lib/systemd/linger/arduino"])
    report.command("Early-start helper enabled", user_systemctl("is-enabled", "--quiet", "virtualglove-early-start.service"))
    report.check("Early-start helper installed", Path("/home/arduino/.local/lib/virtualglove/uno-q-early-start.py").is_file())
    tls = SOURCE / "data/tls"
    authority = tls / "controller-ca-cert.pem"
    authority_key = tls / "controller-ca-key.pem"
    website = tls / "pairing-cert.pem"
    website_key = tls / "pairing-key.pem"
    report.check("Controller trust authority created",
                 authority.is_file() and not authority.is_symlink())
    report.check("Controller authority private key protected",
                 authority_key.is_file() and not authority_key.is_symlink() and
                 authority_key.stat().st_mode & 0o777 == 0o600)
    report.check("HTTPS private key protected",
                 website_key.is_file() and not website_key.is_symlink() and
                 website_key.stat().st_mode & 0o777 == 0o600)
    if authority.is_file() and website.is_file():
        report.command("HTTPS certificate chains to this Controller",
                       ["openssl", "verify", "-CAfile", str(authority), str(website)])
    else:
        report.check("HTTPS certificate chains to this Controller", False)
    status = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8088/status", timeout=3) as response:
            status = json.load(response)
        report.check("Application HTTP status", bool(status.get("version")))
    except (OSError, ValueError):
        report.check("Application HTTP status", False)
    report.check("App-owned Avahi resolver configured", "local:avahi_resolver" in (SOURCE / "app.yaml").read_text() and (SOURCE / "bricks/local/avahi_resolver/brick_compose.yaml").is_file())
    report.command("Profile UDP ingress published", ["docker", "port", "virtualglove-profile-relay-1", "55356/udp"])
    code = ("import json; from pathlib import Path; from virtualglove.resolver import resolve_ipv4; "
            "d=json.loads(Path('/app/data/device.json').read_text()); resolve_ipv4(d['receiver'])")
    if status.get("connection_configured"):
        report.command("Configured receiver resolves inside app", ["docker", "exec", "-e", "PYTHONPATH=/app/src", "virtualglove-main-1", "python3", "-c", code])
    else:
        report.check("Configure your RetroPie destination in Connection", False, pending=True)
    for route in ("help", "help/installation", "help-pdf/installation.pdf"):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8088/" + route, timeout=10) as response:
                report.check("Available: " + route, response.status == 200)
        except OSError:
            report.check("Available: " + route, False)
    report.check("USB camera device present", Path("/dev/v4l/by-id").is_dir() and
                 bool(list(Path("/dev/v4l/by-id").glob("*"))), pending=True)
    report.check("Complete pairing and verify gameplay; credentials remain user-controlled", False, pending=True)


def main():
    """Run installation or read-only checks with an explicit result summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine", choices=("retropie", "recalbox", "batocera", "uno-q"))
    parser.add_argument("--peer", type=valid_host,
                        help="Other machine hostname; required for a new console installation")
    parser.add_argument("--check", action="store_true", help="Read-only checks; install nothing")
    parser.add_argument("--list-player1-devices", action="store_true",
                        help="List configured connected gamepads and install nothing")
    parser.add_argument("--player1-device",
                        help="Stable gamepad ID from --list-player1-devices")
    parser.add_argument("--wifi-status-only", action="store_true", help="Install/update only the UNO Q Wi-Fi status sampler")
    parser.add_argument("--runtime-names-only", action="store_true",
                        help="Migrate only UNO Q host helpers to virtualglove names")
    args = parser.parse_args()
    if (args.wifi_status_only or args.runtime_names_only) and (args.machine != "uno-q" or args.check):
        parser.error("helper-only options require uno-q without --check")
    if args.wifi_status_only and args.runtime_names_only:
        parser.error("choose only one helper-only option")
    if args.list_player1_devices and args.machine not in ("recalbox", "batocera"):
        parser.error("--list-player1-devices applies only to Recalbox and Batocera")
    if args.player1_device and args.machine not in ("recalbox", "batocera"):
        parser.error("--player1-device applies only to Recalbox and Batocera")
    if sys.platform != "linux" or (not args.check and not args.list_player1_devices and os.geteuid() != 0):
        parser.error("Run installation on the target Linux machine with sudo")
    try:
        if args.list_player1_devices:
            list_player1_devices(args.machine)
            return 0
        if args.wifi_status_only:
            install_wifi_status()
            print("Wi-Fi status sampler installed; backups: " + str(BACKUPS))
            return 0
        if args.runtime_names_only:
            install_unoq_runtime_names()
            print("VirtualGlove host helpers installed; backups: " + str(BACKUPS))
            return 0
        if not args.check:
            if args.machine == "retropie":
                required = ("src/virtualglove/receiver.py", "config/games.json",
                            "retropie/virtualglove-receiver.timer")
            elif args.machine == "recalbox":
                required = ("src/virtualglove/receiver.py", "config/games.json",
                            "recalbox/virtualglove-service")
            elif args.machine == "batocera":
                required = ("src/virtualglove/receiver.py", "config/games.json",
                            "recalbox/virtualglove-service", "batocera/VirtualGlove",
                            "batocera/virtualglove-game")
            else:
                required = ("scripts/configure-uno-q-mdns.py", "uno-q/virtualglove-system-shutdown.path")
            for relative in required:
                if not (SOURCE / relative).is_file():
                    raise ValueError("Incomplete project download: missing " + relative)
            if args.machine == "recalbox":
                install_recalbox(args.peer, args.player1_device)
            elif args.machine == "batocera":
                install_batocera(args.peer, args.player1_device)
            else:
                {"retropie": install_retropie, "uno-q": install_unoq}[args.machine](args.peer)
                if args.machine == "uno-q":
                    wait_unoq()
            print("Managed-file backups, when changed: " + str(BACKUPS))
        report = Report()
        {"retropie": check_retropie, "recalbox": check_recalbox,
         "batocera": check_batocera,
         "uno-q": check_unoq}[args.machine](report)
        return report.finish()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("FAIL  Setup stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
