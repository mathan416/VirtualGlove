"""Resolve Router outputs for one RetroArch session; never edit saved configs."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .retroarch_udev import retroarch_udev_event_nodes


def _terminate_with_adapter():
    """Do not orphan RetroArch if a frontend kills the adapter with SIGKILL."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "Cannot protect RetroArch's process lifetime")
    if os.getppid() == 1:  # Parent exited between fork and prctl.
        os.kill(os.getpid(), signal.SIGTERM)


def compatibility(executable: Path) -> str:
    """Require both a known version and reservation keys in the selected binary."""
    try:
        result = subprocess.run([str(executable), "--version"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "legacy-udev"
    version = re.search(r"(?:RetroArch |Version: )(\d+)\.(\d+)\.(\d+)", result.stdout)
    if version and result.returncode == 0 and tuple(map(int, version.groups())) >= (1, 20, 0):
        data = executable.read_bytes()
        if b"reserved_device" in data and b"device_reservation_type" in data:
            return "native-reservations"
    return "legacy-udev"


def resolve(players, sys_root=Path("/sys/class/input"), nodes=None):
    """Match name AND VID/PID; reject duplicates rather than choosing the first."""
    from .controller_router import output_name, DEVICE_PRODUCT_BASE
    events = retroarch_udev_event_nodes() if nodes is None else nodes
    found = {}
    for player in players:
        expected = (output_name(player), 0x1209, DEVICE_PRODUCT_BASE + player)
        matches = []
        for slot, node in enumerate(events):
            device = sys_root / Path(node).name / "device"
            try:
                actual = (device.joinpath("name").read_text().strip(),
                          int(device.joinpath("id/vendor").read_text().strip(), 16),
                          int(device.joinpath("id/product").read_text().strip(), 16))
            except FileNotFoundError:
                continue
            if actual == expected:
                matches.append({"player": player, "name": expected[0],
                                "vendor": expected[1], "product": expected[2],
                                "slot": slot, "event": node})
        if len(matches) > 1:
            raise RuntimeError("Duplicate Router identity for Player %d; stop the duplicate Router service." % player)
        if matches:
            found[player] = matches[0]
    return found


def prepare(config, executable, output, wait_seconds=5.0, resolver=resolve):
    from .controller_router import enabled_players, _player_bindings
    players = config.get("_launch_players", enabled_players(config))
    deadline = time.monotonic() + min(5.0, max(0.0, wait_seconds))
    while True:
        identities = resolver(players)
        if len(identities) == len(players):
            break
        if time.monotonic() >= deadline:
            missing = ", ".join(str(p) for p in players if p not in identities)
            raise RuntimeError("Router outputs missing for Player %s. Check Controller Router's service, then relaunch the game." % missing)
        time.sleep(0.05)
    mode = compatibility(Path(executable))
    lines = ["# Controller Router: temporary session settings", 'input_joypad_driver = "udev"', 'config_save_on_exit = "false"']
    for player, identity in sorted(identities.items()):
        lines.append('input_player%d_joypad_index = "%d"' % (player, identity["slot"]))
        lines.extend('%s = "%s"' % (key, value)
                     for key, value in _player_bindings(player).items()
                     if key != "input_enable_hotkey_btn")
        if player == 1:
            lines.append('input_enable_hotkey_btn = "12"')
            if config.get("platform") == "recalbox":
                # Recalbox's saved quit index belongs to the physical pad.
                # The merged output has its own stable Start index.
                lines.append('input_exit_emulator_btn = "11"')
        if mode == "native-reservations":
            # RetroArch treats a VID:PID prefix as a wildcard for the name.
            # Reserve the unique name; resolve() separately validates VID/PID.
            lines.extend(['input_player%d_reserved_device = "%s"' % (player, identity["name"]),
                          'input_player%d_device_reservation_type = "2"' % player])
    if mode == "native-reservations":
        # RetroArch 1.20's reservation allocator indexes an inverse map for
        # ALL 16 slots. Duplicate initial indexes leave holes uninitialized
        # and can crash it, even before the reserved pad is detected. Seed a
        # full permutation, keeping every configured output pinned correctly.
        used = {identity["slot"] for identity in identities.values()}
        if any(slot not in range(16) for slot in used):
            raise RuntimeError("Router output exceeds RetroArch's supported 16 device slots")
        for player in range(1, 17):
            if player in identities:
                continue
            preferred = player - 1
            slot = preferred if preferred not in used else next(index for index in range(16) if index not in used)
            used.add(slot)
            lines.append('input_player%d_joypad_index = "%d"' % (player, slot))
    Path(output).write_text("\n".join(lines) + "\n")
    return {"mode": mode, "controllers": list(identities.values())}


def append_settings(arguments, path):
    """Keep existing appended configs in order; Router settings come last."""
    args = list(arguments)
    existing = []
    remaining = []
    i = 0
    while i < len(args):
        item = args[i]
        if item == "--appendconfig":
            if i + 1 == len(args):
                raise ValueError("--appendconfig requires a filename")
            existing.append(args[i + 1]); i += 2
        elif item.startswith("--appendconfig="):
            existing.append(item.split("=", 1)[1]); i += 1
        else:
            remaining.append(item); i += 1
    return remaining + ["--appendconfig", "|".join(existing + [str(path)])]


def launch_core(arguments):
    for index, value in enumerate(arguments):
        if value.startswith("--libretro="):
            return Path(value.split("=", 1)[1]).name.casefold()
        if value in ("-L", "--libretro") and index + 1 < len(arguments):
            return Path(arguments[index + 1]).name.casefold()
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--retroarch", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--system")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    from .controller_router import load_config, routes_physical_core
    try:
        if Path('/run/controller-router/pairing.pending').exists():
            raise RuntimeError('A console connection is being updated. Wait for pairing to finish, then launch again.')
        if not args.config.exists():
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            if args.output:
                raise RuntimeError("Controller Router is not configured")
            os.execv(str(args.retroarch), [str(args.retroarch)] + arguments)
        try:
            config = load_config(args.config)
        except PermissionError:
            manifest = json.loads(Path("/run/virtualglove/controller-router-launch.json").read_text())
            if manifest.get("schema") != 1 or not isinstance(manifest.get("outputs"), list) or any(
                    type(player) is not int or player not in (1, 2, 3, 4) for player in manifest["outputs"]):
                raise ValueError("Invalid Router launch manifest; restart the service")
            from .systems import policy
            scope, selected = policy(manifest)
            config = {"players": [], "virtualglove_player": None, "_launch_players": manifest["outputs"],
                      "physical_scope": scope, "physical_systems": selected}
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        from .systems import argument_system, system_id
        system = system_id(args.system) if args.system else argument_system(arguments)
        if system:
            os.environ['CONTROLLER_ROUTER_SYSTEM'] = system
        else:
            os.environ.pop('CONTROLLER_ROUTER_SYSTEM', None)
        if not args.output and not routes_physical_core(config, launch_core(arguments), system):
            # Out-of-scope systems keep the frontend's original arguments and
            # physical controller assignments, with no appended Router settings.
            os.execv(str(args.retroarch), [str(args.retroarch)] + arguments)
        if args.output:
            print(json.dumps(prepare(config, args.retroarch, args.output)))
            return 0
        with tempfile.TemporaryDirectory(prefix="controller-router-session-") as folder:
            settings = Path(folder) / "routing.cfg"
            report = prepare(config, args.retroarch, settings)
            report["system"] = system
            print("Controller Router: " + json.dumps(report), file=sys.stderr, flush=True)
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            process = subprocess.Popen([str(args.retroarch)] + append_settings(arguments, settings),
                                       preexec_fn=_terminate_with_adapter if sys.platform.startswith("linux") else None)
            # Do not restart Router/output devices during this session.
            old = {}
            for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                old[number] = signal.signal(number, lambda sig, frame: process.send_signal(sig))
            warned = False
            try:
                while process.poll() is None:
                    if not warned:
                        try:
                            current = resolve([entry["player"] for entry in report["controllers"]])
                            if any(not current.get(entry["player"]) or any(
                                    current[entry["player"]].get(key) != entry.get(key)
                                    for key in ("event", "name", "vendor", "product"))
                                   for entry in report["controllers"]):
                                raise RuntimeError("output identity changed")
                        except (OSError, RuntimeError):
                            print("Controller Router outputs were lost. End this game and relaunch after the service is ready.", file=sys.stderr, flush=True)
                            warned = True
                    time.sleep(0.25)
                return process.returncode
            finally:
                for number, handler in old.items():
                    signal.signal(number, handler)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("Controller Router launch blocked: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
