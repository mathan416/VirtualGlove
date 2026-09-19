#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/install-package.py
# Purpose: Validate and stage a release, preserving local settings before host setup.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Made virtualglove the canonical App Lab directory and added recoverable legacy migration.
#   2026-09-11 - Prevented renamed and legacy App Lab projects from overlapping on upgrade.
#   2026-09-11 - Added safe, optional first-install Controller naming.
#   2026-09-11 - Printed hostname and LAN-IP Controller URLs after UNO Q installation.
#   2026-09-11 - Install checksum-verified precompiled Matrix firmware without a compiler.
#   2026-09-11 - Prevented the verified setup loader from writing cache files into release staging.
#   2026-09-05 - Required the complete renewable game-session implementation.
#   2026-09-04 - Added versioned multi-machine installation.
# Full history: docs/CHANGELOG.md and Git history.

"""Install a downloaded, checksum-verified package on its intended Linux host."""
import argparse
import importlib.util
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

APP = Path("/home/arduino/ArduinoApps/virtualglove")
RETROPIE_LAUNCHER = Path("/etc/virtualglove/launcher.json")
RECALBOX_LAUNCHER = Path("/recalbox/share/system/virtualglove/data/launcher.json")
BATOCERA_LAUNCHER = Path("/userdata/system/virtualglove/data/launcher.json")
LEGACY_RUNTIME_MEMBERS = {
    "retropie/powerglove-receiver.service",
    "retropie/powerglove-receiver.timer",
    "retropie/powerglove-games.service",
    "retropie/runcommand-onstart-powerglove.sh",
    "retropie/runcommand-onend-powerglove.sh",
    *{"retropie/bin/powerglove-" + name for name in (
        "bsb-zap", "dot", "games", "pair", "profile", "receiver", "retropie-hook"
    )},
    *{"uno-q/powerglove-" + name for name in (
        "early-start.service", "wifi-status.py", "wifi-status.service", "wifi-status.timer",
        "system-shutdown.conf", "system-shutdown.path", "system-shutdown.service",
        "camera-recovery.py", "camera-recovery.conf", "camera-recovery.path",
        "camera-recovery.service",
    )},
}


def retropie_launcher_exists(current=RETROPIE_LAUNCHER):
    """Recognize an existing supported VirtualGlove installation."""
    return current.is_file()


def controller_addresses():
    """Return the stable mDNS name and usable host IPv4 addresses."""
    hostname = socket.gethostname().split(".", 1)[0] + ".local"
    addresses = []
    try:
        result = subprocess.check_output(
            ["ip", "-j", "-4", "address", "show", "up"], timeout=5)
        interfaces = json.loads(result)
        for interface in interfaces:
            name = str(interface.get("ifname", "")).lower()
            if (name == "lo" or name.startswith(("docker", "br-", "veth", "virbr"))):
                continue
            for address in interface.get("addr_info", []):
                if address.get("family") != "inet" or address.get("scope") != "global":
                    continue
                try:
                    value = ipaddress.ip_address(address.get("local", ""))
                except ValueError:
                    continue
                if (value.version == 4 and not value.is_loopback and
                        not value.is_link_local and not value.is_multicast and
                        str(value) not in addresses):
                    addresses.append(str(value))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError,
            json.JSONDecodeError):
        pass
    return hostname, addresses


def print_controller_urls(controller_hostname=None):
    """Show friendly entry points without making network discovery an install gate."""
    hostname, addresses = controller_addresses()
    if controller_hostname:
        hostname = controller_hostname + ".local"
    print("\nVirtualGlove Controller is ready. Open one of these addresses:")
    for label, address in [("Hostname", hostname)] + [("IP address", value) for value in addresses]:
        print("\n  " + label + ":")
        print("    Dashboard  http://" + address + ":8088/dashboard")
        print("    Setup      https://" + address + ":8443/setup")
        print("    Help       http://" + address + ":8088/help")
    if not addresses:
        print("\n  IP address: not available yet; connect Ethernet or Wi-Fi and use the hostname above.")


def load_setup(source):
    """Load the verified host installer without mutating its release staging tree."""
    spec = importlib.util.spec_from_file_location("setup_machine", source / "scripts/setup-machine.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def unpack(archive, destination, machine, version):
    """Reject unsafe paths, special files, duplicate names and wrong release identities."""
    with zipfile.ZipFile(archive) as package:
        seen = set()
        total = 0
        for item in package.infolist():
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (not path.parts or path.parts[0] != "VirtualGlove" or path.is_absolute()
                    or ".." in path.parts or "\\" in item.filename or item.filename in seen
                    or str(path) != item.filename.rstrip("/")
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                raise ValueError("Unsafe or duplicate package member: " + item.filename)
            if set(path.parts[1:]) & {"data", ".cache", ".git", ".venv", "__pycache__"} or path.name == "cheatsheet.md" or any(part.startswith(".virtualglove-install") for part in path.parts):
                raise ValueError("Package contains private or generated files")
            if str(PurePosixPath(*path.parts[1:])) in LEGACY_RUNTIME_MEMBERS:
                raise ValueError("Package contains a legacy PowerGlove runtime file: " + item.filename)
            total += item.file_size
            if total > 2 * 1024 ** 3:
                raise ValueError("Package expands beyond 2 GiB")
            seen.add(item.filename)
        meta = json.loads(package.read("VirtualGlove/install-release.json"))
        if meta != {"format": 1, "machine": machine, "version": version}:
            raise ValueError("Package version or target does not match the requested release")
        required = [
            "scripts/setup-machine.py",
            "scripts/installation-manifest.py",
            "src/virtualglove/receiver.py",
            "src/virtualglove/gesture.py",
            "src/virtualglove/tracker.py",
            "src/virtualglove/tuning.py",
            "src/virtualglove/vision_app.py",
            "src/virtualglove/profile_control.py",
            "config/games.json",
            "config/profiles.json",
            "THIRD_PARTY_NOTICES.md",
        ]
        required += (["app.yaml", "scripts/flash-matrix-firmware.py",
                      "firmware/matrix/manifest.json", "firmware/matrix/virtualglove-matrix.elf-zsk.bin",
                      "firmware/matrix/zephyr-arduino_uno_q_stm32u585xx.elf",
                      "firmware/matrix/flash_sketch.cfg", "scripts/uno-q-early-start.py",
                      "uno-q/virtualglove-early-start.service",
                      "uno-q/virtualglove-wifi-status.py", "uno-q/virtualglove-wifi-status.service",
                      "uno-q/virtualglove-wifi-status.timer",
                      "uno-q/virtualglove-system-shutdown.conf", "uno-q/virtualglove-system-shutdown.path",
                      "uno-q/virtualglove-system-shutdown.service",
                      "uno-q/virtualglove-camera-recovery.py", "uno-q/virtualglove-camera-recovery.conf",
                      "uno-q/virtualglove-camera-recovery.path", "uno-q/virtualglove-camera-recovery.service"]
                     if machine == "uno-q" else ([
                         "src/virtualglove/console_monitor.py",
                         "src/virtualglove/merged_gamepad.py",
                         "src/virtualglove/controller_router.py",
                         "recalbox/virtualglove-service",
                         "recalbox/virtualglove-core-mount",
                         "scripts/build-recalbox-nestopia-powerglove.sh",
                         "scripts/build-recalbox-native-matrix.sh",
                         "scripts/install-recalbox-nestopia-powerglove.sh",
                         "scripts/configure-recalbox-super-glove-ball-core.py",
                         "scripts/verify-recalbox-native-core.py",
                         "native/recalbox/manifest.json",
                         "native/nestopia-powerglove/nestopia-powerglove.patch",
                         "python/ssh_pair.py",
                     ] if machine == "recalbox" else ([
                         "src/virtualglove/merged_gamepad.py",
                         "src/virtualglove/controller_router.py",
                         "src/virtualglove/retropie_hook.py",
                         "recalbox/virtualglove-service",
                         "batocera/VirtualGlove",
                         "batocera/virtualglove-game",
                         "batocera/virtualglove-core-mount",
                         "scripts/build-batocera-nestopia-powerglove.sh",
                         "scripts/build-batocera-native-matrix.sh",
                         "scripts/install-batocera-nestopia-powerglove.sh",
                         "scripts/configure-batocera-super-glove-ball-core.py",
                         "scripts/verify-batocera-native-core.py",
                         "native/batocera/manifest.json",
                         "native/nestopia-powerglove/nestopia-powerglove.patch",
                         "python/ssh_pair.py",
                     ] if machine == "batocera" else [
                         "retropie/virtualglove-receiver.service",
                         "retropie/virtualglove-receiver.timer",
                         "retropie/virtualglove-controller-router.service",
                         "retropie/virtualglove-games.service",
                         "src/virtualglove/retropie_hook.py",
                         "retropie/bin/virtualglove-retropie-hook",
                         "retropie/bin/virtualglove-receiver",
                         "retropie/bin/virtualglove-games",
                         "retropie/bin/virtualglove-pair",
                         "retropie/bin/virtualglove-profile",
                         "retropie/bin/virtualglove-bsb-zap",
                         "retropie/runcommand-onstart-virtualglove.sh",
                         "retropie/runcommand-onend-virtualglove.sh",
                         "scripts/install-nestopia-powerglove.sh",
                         "scripts/install-powerglove-dot.sh",
                         "scripts/configure-super-glove-ball-core.py",
                         "native/nestopia-powerglove/nestopia-powerglove.patch",
                         "native/powerglove-dot/powerglove_dot.cpp",
                         "src/virtualglove/dot_launcher.py",
                         "retropie/bin/virtualglove-dot",
                     ])))
        if machine == "recalbox":
            native = json.loads(package.read("VirtualGlove/native/recalbox/manifest.json"))
            if native.get("format") != 2 or not isinstance(native.get("cores"), dict):
                raise ValueError("Incomplete package: malformed Recalbox native-core manifest")
            valid_targets = {"rpizero2", "rpi3", "rpi4_64", "rpi5_64",
                             "rg353x", "odroidgo2", "x86_64"}
            for target, versions in native["cores"].items():
                if target not in valid_targets or not isinstance(versions, dict):
                    raise ValueError("Incomplete package: malformed Recalbox native-core target")
                for native_version, entry in versions.items():
                    if (not re.fullmatch(r"10(?:\.[0-9]+)+", native_version)
                            or not isinstance(entry, dict)):
                        raise ValueError("Incomplete package: malformed Recalbox native-core version")
                    for field in ("file", "source_file"):
                        relative = entry.get(field)
                        path = PurePosixPath(relative) if isinstance(relative, str) else None
                        if (path is None or path.is_absolute() or ".." in path.parts
                                or path.parts[:2] != (target, native_version)):
                            raise ValueError("Incomplete package: unsafe Recalbox native-core path")
                        required.append("native/recalbox/" + str(path))
        if machine == "batocera":
            native = json.loads(package.read("VirtualGlove/native/batocera/manifest.json"))
            if native.get("format") != 2 or not isinstance(native.get("cores"), dict):
                raise ValueError("Incomplete package: malformed Batocera native-core manifest")
            valid_targets = {"bcm2835", "bcm2836", "bcm2837", "bcm2711", "bcm2712",
                             "x86_64", "rk3326", "rk3399", "rk3568", "rk3588", "s905",
                             "s905gen2", "s905gen3", "s922x", "sm8250"}
            for target, versions in native["cores"].items():
                if target not in valid_targets or not isinstance(versions, dict):
                    raise ValueError("Incomplete package: malformed Batocera native-core target")
                for native_version, entry in versions.items():
                    if (not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", native_version)
                            or not isinstance(entry, dict)):
                        raise ValueError("Incomplete package: malformed Batocera native-core version")
                    required_fields = {
                        "file", "sha256", "size", "elf_class", "elf_machine",
                        "source_file", "source_sha256", "source_size",
                        "batocera_version", "batocera_revision", "nestopia_revision",
                        "patch_sha256", "build_image",
                    }
                    if (set(entry) != required_fields
                            or entry.get("batocera_version") != native_version
                            or not isinstance(entry.get("size"), int) or entry["size"] <= 0
                            or not isinstance(entry.get("source_size"), int)
                            or entry["source_size"] <= 0
                            or entry.get("elf_class") not in (32, 64)
                            or entry.get("elf_machine") not in ("arm", "aarch64", "x86_64")
                            or any(not isinstance(entry.get(field), str)
                                   or not re.fullmatch(r"[0-9a-f]{64}", entry[field])
                                   for field in ("sha256", "source_sha256", "patch_sha256"))
                            or any(not isinstance(entry.get(field), str)
                                   or not re.fullmatch(r"[0-9a-f]{40}", entry[field])
                                   for field in ("batocera_revision", "nestopia_revision"))
                            or not isinstance(entry.get("build_image"), str)
                            or "@sha256:" not in entry["build_image"]):
                        raise ValueError("Incomplete package: malformed Batocera native-core entry")
                    for field in ("file", "source_file"):
                        relative = entry.get(field)
                        path = PurePosixPath(relative) if isinstance(relative, str) else None
                        if (path is None or path.is_absolute() or ".." in path.parts
                                or path.parts[:2] != (target, native_version)):
                            raise ValueError("Incomplete package: unsafe Batocera native-core path")
                        required.append("native/batocera/" + str(path))
        for relative in required:
            if "VirtualGlove/" + relative not in seen:
                raise ValueError("Incomplete package: " + relative)
        if machine == "uno-q":
            firmware = json.loads(package.read("VirtualGlove/firmware/matrix/manifest.json"))
            build = json.loads(package.read("VirtualGlove/src/virtualglove/_build_info.json"))
            if not isinstance(firmware, dict) or not isinstance(build, dict):
                raise ValueError("Invalid Matrix firmware or application identity")
            if firmware.get("firmware_source_id") != build.get("firmware_expected"):
                raise ValueError("Matrix firmware does not match the packaged application")
        package.extractall(str(destination))
        for item in package.infolist():
            if not item.is_dir():
                (destination / item.filename).chmod(0o755 if item.external_attr >> 16 & 0o111 else 0o644)
    return destination / "VirtualGlove"


def confirm(message):
    """Require an interactive answer for an interruption or optional configuration change."""
    if not sys.stdin.isatty():
        return False
    return input(message + " [y/N] ").strip().lower() in ("y", "yes")


def valid_controller_hostname(value):
    """Normalize one safe mDNS host label used only during a fresh installation."""
    value = str(value).strip().lower()
    if value.endswith(".local"):
        value = value[:-6]
    if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value)
            or value.isdigit() or value in ("local", "localhost", "broadcasthost")):
        raise argparse.ArgumentTypeError(
            "Use 1-63 letters, numbers, or internal hyphens, such as virtualglove")
    return value


def select_controller_hostname(requested, existing_install):
    """Choose a hostname only for a first install; upgrades never rename the board."""
    current = socket.gethostname().split(".", 1)[0].lower()
    if existing_install:
        if requested is not None:
            raise ValueError(
                "--hostname is only for a first installation; the existing Controller name was preserved")
        return None
    if requested is not None:
        return valid_controller_hostname(requested)
    if not sys.stdin.isatty():
        print("ACTION  Non-interactive first install: preserving Controller name " + current + ".")
        return None
    print("\nName this VirtualGlove Controller.")
    print("Its local address will be NAME.local. Press Enter for the recommended name.")
    chosen = valid_controller_hostname(input("Controller name [virtualglove]: ").strip()
                                       or "virtualglove")
    answer = input("Use " + chosen + ".local? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        raise ValueError("No changes made; Controller name was not confirmed")
    return chosen


def local_ipv4_addresses():
    """Return physical host IPv4 addresses for conflict comparison."""
    return set(controller_addresses()[1])


def hostname_conflicts(name):
    """Report a visible mDNS name owned by a different LAN address."""
    try:
        result = subprocess.check_output(
            ["getent", "ahostsv4", name + ".local"], timeout=4,
            stderr=subprocess.DEVNULL).decode(errors="replace")
    except subprocess.CalledProcessError:
        return False
    except (OSError, subprocess.TimeoutExpired):
        print("ACTION  Could not check the LAN for a matching name; continuing with "
              + name + ".local.")
        return False
    resolved = {line.split()[0] for line in result.splitlines() if line.split()}
    return bool(resolved - local_ipv4_addresses())


def hosts_with_controller_name(text, old_name, new_name):
    """Update only the conventional local-host identity while preserving aliases/comments."""
    lines = text.splitlines(True)
    found = False
    for index, line in enumerate(lines):
        body, marker, comment = line.partition("#")
        fields = body.split()
        if fields and fields[0] == "127.0.1.1":
            aliases = [new_name if item.lower() in
                       (old_name.lower(), old_name.lower() + ".local") else item
                       for item in fields[1:]]
            if new_name not in [item.lower() for item in aliases]:
                aliases.insert(0, new_name)
            rebuilt = "127.0.1.1\t" + " ".join(aliases)
            if marker:
                rebuilt += " #" + comment.rstrip("\n")
            lines[index] = rebuilt + "\n"
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append("127.0.1.1\t" + new_name + "\n")
    return "".join(lines)


def configure_controller_hostname(setup, name):
    """Persist a confirmed fresh-install hostname with recoverable file backups."""
    if not name:
        return None
    old_name = socket.gethostname().split(".", 1)[0]
    if name == old_name.lower():
        return name
    if hostname_conflicts(name):
        raise ValueError(name + ".local is already in use on this network; choose another name")
    setup.write_file("/etc/hostname", name + "\n")
    hosts = Path("/etc/hosts")
    if hosts.is_file() and not hosts.is_symlink():
        setup.write_file(hosts, hosts_with_controller_name(hosts.read_text(), old_name, name))
    setup.run("hostnamectl", "set-hostname", name)
    print("ACTION  Controller name set to " + name + ".local.")
    return name


def preflight(machine):
    """Check target identity and supported prerequisites before any host changes."""
    if sys.platform != "linux" or os.geteuid() != 0 or sys.version_info < (3, 7):
        raise ValueError("Installation requires Linux, Python 3.7+, and sudo")
    commands = (("apt-get", "systemctl", "hostnamectl") if machine == "uno-q" else
                (("apt-get", "systemctl") if machine == "retropie" else ("python3",)))
    for command in commands:
        if not shutil.which(command):
            raise ValueError("Missing system command: " + command)
    staging = (pwd.getpwnam("arduino").pw_dir if machine == "uno-q" else
               ("/recalbox/share" if machine == "recalbox" else
                ("/userdata" if machine == "batocera" else "/var/tmp")))
    if shutil.disk_usage(staging).free < 3 * 1024 ** 3:
        raise ValueError("At least 3 GiB free space is required on " + str(staging))
    backup_root = ({"recalbox": "/recalbox/share", "batocera": "/userdata"}.get(
        machine, "/var/backups"))
    if shutil.disk_usage(backup_root).free < 512 * 1024 ** 2:
        raise ValueError("At least 512 MiB free space is required for installation and backups")
    if machine == "uno-q":
        compatible = Path("/proc/device-tree/compatible").read_bytes()
        if b"arduino,imola" not in compatible:
            raise ValueError("This installer supports the Arduino UNO Q only")
        pwd.getpwnam("arduino")
        if not shutil.which("arduino-app-cli") or not Path("/opt/openocd/bin/openocd").is_file():
            raise ValueError("Complete board provisioning with Arduino App Lab first")
        result = subprocess.check_output(["runuser", "-u", "arduino", "--", "arduino-app-cli", "version"], timeout=20).decode()
        versions = re.findall(r"(?:CLI version|daemon version:)\s+([0-9.]+)", result, re.IGNORECASE)
        if versions != ["0.13.0", "0.13.0"]:
            raise ValueError("This release is validated with App Lab CLI 0.13.0; consult its compatibility guide")
        if (APP / "data/shutdown-request").exists():
            raise ValueError("Pending shutdown request; resolve it before installation")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8088/status", timeout=3) as response:
                status = json.load(response)
        except OSError:
            status = None
        if APP.exists() and status is None:
            if not confirm("Cannot determine application activity. Continue with an app restart?"):
                raise ValueError("No changes made; could not confirm safe restart")
        elif status and (status.get("controller_enabled") or status.get("practice_mode") or
                         status.get("tuning", {}).get("active") or status.get("profile", "off") != "off"):
            if not confirm("VirtualGlove is active. Interrupt this session and install?"):
                raise ValueError("No changes made; active session preserved")
    elif machine == "retropie":
        if not Path("/opt/retropie/configs/all").is_dir():
            raise ValueError("Install and configure RetroPie first")
        running = subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL)
        if running.returncode != 1:
            if not confirm("RetroArch may be running. Close the game, then confirm to continue"):
                raise ValueError("No changes made; close RetroArch and retry")
            if subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL).returncode != 1:
                raise ValueError("RetroArch is still running; no changes made")
    elif machine == "recalbox":
        if not Path("/recalbox/recalbox.version").is_file():
            raise ValueError("Install and start Recalbox first")
        if not Path("/recalbox/recalbox.version").read_text().strip().startswith("10."):
            raise ValueError("This release supports Recalbox 10.x")
        if subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError("Close the running game before installing VirtualGlove")
    else:
        version = Path("/usr/share/batocera/batocera.version")
        match = re.search(r"\d+", version.read_text()) if version.is_file() else None
        if not match or int(match.group()) < 38:
            raise ValueError("Batocera 38 or newer is required")
        if not shutil.which("batocera-services"):
            raise ValueError("Missing system command: batocera-services")
        if subprocess.run(["pgrep", "-x", "retroarch"], stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError("Close the running game before installing VirtualGlove")


def stop_managed_runtime(machine, setup):
    """Stop console publishers before replacing any managed runtime files."""
    if machine == "uno-q":
        return None
    present = False
    if machine == "retropie":
        units = ("virtualglove-receiver.timer", "virtualglove-receiver.service",
                 "virtualglove-games.service")
        present = any(Path("/etc/systemd/system", unit).exists() for unit in units)
        for unit in units:
            subprocess.run(["systemctl", "stop", unit], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif machine == "recalbox":
        service = Path("/recalbox/share/system/virtualglove/recalbox/virtualglove-service")
        present = service.is_file()
        if present:
            subprocess.run(["sh", str(service), "stop"], check=True)
    else:
        service = Path("/userdata/system/services/VirtualGlove")
        present = service.is_file()
        if present:
            subprocess.run(["batocera-services", "stop", "VirtualGlove"], check=False)
    deadline = time.monotonic() + 5
    while setup.managed_runtime_processes() and time.monotonic() < deadline:
        time.sleep(0.1)
    remaining = setup.managed_runtime_processes()
    if remaining:
        raise ValueError("Could not stop existing VirtualGlove runtime processes: " +
                         ", ".join(map(str, remaining)))
    return machine if present else None


def restart_managed_runtime(machine):
    """Best-effort recovery when an upgrade fails after stopping an old runtime."""
    if machine == "retropie":
        subprocess.run(["systemctl", "start", "virtualglove-games.service"], check=False)
        subprocess.run(["systemctl", "start", "virtualglove-receiver.timer"], check=False)
        token = Path("/etc/virtualglove/token")
        if token.is_file() and len(token.read_text().strip()) >= 16:
            subprocess.run(["systemctl", "start", "virtualglove-receiver.service"], check=False)
    elif machine == "recalbox":
        service = Path("/recalbox/share/system/virtualglove/recalbox/virtualglove-service")
        if service.is_file():
            subprocess.run(["sh", str(service), "start"], check=False)
    elif machine == "batocera":
        subprocess.run(["batocera-services", "start", "VirtualGlove"], check=False)


def stage_unoq(source, setup):
    """Back up managed app files and update them without touching data or local documents."""
    user = pwd.getpwnam("arduino")
    for directory in (APP, APP.parent):
        if directory.is_symlink():
            raise ValueError("Refusing symbolic application directory")
    files = [path for path in source.rglob("*") if path.is_file()]
    for path in files:
        target = APP / path.relative_to(source)
        if any(parent.is_symlink() for parent in [target] + list(target.parents)):
            raise ValueError("Refusing symbolic installation path: " + str(target))
    cache = APP / ".cache/sketch"
    if cache.is_dir() and not (setup.BACKUPS / "previous-sketch-cache").exists():
        shutil.copytree(str(cache), str(setup.BACKUPS / "previous-sketch-cache"), symlinks=True)
    compose = APP / ".cache/app-compose.yaml"
    if compose.exists():
        setup.run("runuser", "-u", "arduino", "--", "arduino-app-cli",
                  "app", "stop", APP)
        setup.run("env", "APP_HOME=" + str(APP), "docker", "compose",
                  "-p", "virtualglove", "-f", compose, "down", "--remove-orphans")
    APP.mkdir(parents=True, exist_ok=True)
    setup.installation_manifest()["apply"](source, APP, setup.BACKUPS / "application-payload")
    sketch_directory = APP / "sketch"
    if sketch_directory.is_dir():
        if any(sketch_directory.iterdir()):
            raise ValueError("Unmanaged files remain in the retired sketch directory: "
                             + str(sketch_directory))
        sketch_directory.rmdir()
    for path in files:
        target = APP / path.relative_to(source)
        os.chown(str(target), user.pw_uid, user.pw_gid)
        for parent in target.parents:
            if parent == APP.parent:
                break
            os.chown(str(parent), user.pw_uid, user.pw_gid)
    for name in (".virtualglove-install.json", ".virtualglove-install.lock"):
        os.chown(str(APP / name), user.pw_uid, user.pw_gid)
    setup.SOURCE = APP
    # Flash through factory OpenOCD. The release carries no compiler or sketch source.
    setup.run("python3", APP / "scripts/flash-matrix-firmware.py", APP / "firmware/matrix")
    # Starting an app without sketch/ starts its Linux services without compiling.
    setup.run("runuser", "-u", "arduino", "--", "arduino-app-cli", "app", "start", APP)


def main(argv=None):
    """Install validated release files, complete host setup, then report next steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine", choices=("uno-q", "retropie", "recalbox", "batocera"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--peer")
    parser.add_argument("--hostname")
    parser.add_argument("--player1-device")
    parser.add_argument("--list-player1-devices", action="store_true")
    args = parser.parse_args(argv)
    setup = None
    try:
        if args.machine != "uno-q" and args.hostname is not None:
            raise ValueError("--hostname applies only to the VirtualGlove Controller installer")
        if ((args.player1_device or args.list_player1_devices) and
                args.machine not in ("recalbox", "batocera")):
            raise ValueError("Player 1 selection applies only to Recalbox and Batocera")
        existing_install = APP.exists() if args.machine == "uno-q" else False
        selected_hostname = (select_controller_hostname(args.hostname, existing_install)
                             if args.machine == "uno-q" else None)
        preflight(args.machine)
        temporary_root = (pwd.getpwnam("arduino").pw_dir if args.machine == "uno-q" else
                          ({"retropie": "/var/tmp", "recalbox": "/recalbox/share/system",
                            "batocera": "/userdata/system"}[args.machine]))
        with tempfile.TemporaryDirectory(prefix="virtualglove-install-",
                                         dir=temporary_root) as temporary:
            source = unpack(args.archive, Path(temporary), args.machine, args.version)
            setup = load_setup(source)
            if args.peer:
                setup.valid_host(args.peer)
            if args.list_player1_devices:
                if args.machine not in ("recalbox", "batocera"):
                    raise ValueError("--list-player1-devices applies only to Recalbox and Batocera")
                setup.list_player1_devices(args.machine)
                return 0
            launcher_exists = (retropie_launcher_exists() if args.machine == "retropie" else
                               (RECALBOX_LAUNCHER.is_file() if args.machine == "recalbox" else
                                (BATOCERA_LAUNCHER.is_file() if args.machine == "batocera" else True)))
            if args.machine in ("retropie", "recalbox", "batocera") and not launcher_exists and not args.peer:
                if not sys.stdin.isatty():
                    raise ValueError("First console installation requires --peer UNO-Q-NAME.local")
                args.peer = setup.valid_host(input("UNO Q hostname or IP address: ").strip())
            setup.BACKUPS.mkdir(parents=True, mode=0o700)
            setup.BACKUPS.chmod(0o700)
            print("Backups: " + str(setup.BACKUPS), flush=True)
            (setup.BACKUPS / "RESTORE.txt").write_text(
                "Stop VirtualGlove before recovery. Saved paths below mirror absolute host paths.\n"
                "Copy only the files you need back to those paths, retaining ownership/permissions.\n"
                "Private settings were preserved in place. To recover code/firmware, rerun the previous release installer.\n"
                "Then reload systemd and rerun the installer --check. Do not copy the entire backup over /.\n")
            stopped_runtime = stop_managed_runtime(args.machine, setup)
            try:
                if args.machine == "uno-q":
                    active_hostname = configure_controller_hostname(setup, selected_hostname)
                    stage_unoq(source, setup)
                    setup.install_unoq(args.peer)
                    setup.wait_unoq()
                elif args.machine == "retropie":
                    setup.install_retropie(args.peer)
                    setup.configure_games(confirm)
                elif args.machine == "recalbox":
                    setup.install_recalbox(args.peer, args.player1_device)
                else:
                    setup.install_batocera(args.peer, args.player1_device)
            except BaseException:
                if stopped_runtime:
                    restart_managed_runtime(stopped_runtime)
                raise
            report = setup.Report()
            {"uno-q": setup.check_unoq, "retropie": setup.check_retropie,
             "recalbox": setup.check_recalbox,
             "batocera": setup.check_batocera}[args.machine](report)
            if args.machine == "uno-q":
                print_controller_urls(active_hostname)
            else:
                token = ({"retropie": Path("/etc/virtualglove/token"),
                          "recalbox": Path("/recalbox/share/system/virtualglove/data/token"),
                          "batocera": Path("/userdata/system/virtualglove/data/token")}[args.machine])
                if not token.is_file() or len(token.read_text().strip()) < 16:
                    if args.machine == "retropie":
                        print("NEXT  Pair using sudo /opt/virtualglove/bin/virtualglove-pair.")
                    else:
                        command = ("sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service pair"
                                   if args.machine == "recalbox" else
                                   "/userdata/system/services/VirtualGlove pair")
                        print("NEXT  On this console, run " + command + ", then use the one-time code in Controller Setup.")
                print("NEXT  Test VirtualGlove and the physical Player 1 joypad together in FCEUmm.")
            return report.finish()
    except (OSError, ValueError, KeyError, argparse.ArgumentTypeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print("FAIL  Installation stopped: " + str(error), file=sys.stderr)
        if setup:
            print("Recovery instructions and changed-file backups: " + str(setup.BACKUPS), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
