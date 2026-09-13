# Project: VirtualGlove
# File: tests/test_profile_relay.py
# Purpose: Verify bounded UDP relay exchanges and fail-open game-launch reporting.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-06 - Use Python 3.7-compatible mock call argument access.
#   2026-09-05 - Covered detached registered-game lease refresh and cleanup.
#   2026-09-04 - Covered concurrent replies, invalid traffic, capacity expiry and hook failures.

"""Exercise profile transport without hardware or private device settings."""

import contextlib
import importlib.util
import io
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from powerglove_vision import retropie_hook
from powerglove_vision.profile_control import ProfileCommandServer, send_request

spec = importlib.util.spec_from_file_location("profile_relay", Path(__file__).resolve().parents[1] / "scripts/profile-relay.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RelayTests(unittest.TestCase):
    @contextlib.contextmanager
    def running_relay(self, upstream, **kwargs):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.bind(("127.0.0.1", 0))
            stopped = threading.Event()
            thread = threading.Thread(target=module.relay, args=(listener, upstream, stopped), kwargs=kwargs)
            thread.start()
            try:
                yield listener.getsockname()
            finally:
                stopped.set()
                thread.join(2)
                self.assertFalse(thread.is_alive())

    def test_concurrent_clients_get_only_their_reply(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as worker:
            worker.bind(("127.0.0.1", 0))
            worker.settimeout(1)
            with self.running_relay(worker.getsockname()) as address:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                    a.settimeout(1); b.settimeout(1)
                    a.sendto(b"first", address); b.sendto(b"second", address)
                    requests = [worker.recvfrom(4096), worker.recvfrom(4096)]
                    for data, peer in reversed(requests):
                        worker.sendto(data + b"-ack", peer)
                    self.assertEqual(a.recv(4096), b"first-ack")
                    self.assertEqual(b.recv(4096), b"second-ack")

    def test_oversize_dropped_and_capacity_recovers_after_expiry(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as worker, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            worker.bind(("127.0.0.1", 0)); worker.settimeout(0.1)
            with self.running_relay(worker.getsockname(), timeout=0.15, max_pending=1) as address:
                client.sendto(b"x" * 4097, address)
                with self.assertRaises(socket.timeout): worker.recvfrom(5000)
                client.sendto(b"expires", address)
                self.assertEqual(worker.recvfrom(4096)[0], b"expires")
                client.sendto(b"over-capacity", address)
                with self.assertRaises(socket.timeout): worker.recvfrom(5000)
                time.sleep(0.15)
                client.sendto(b"after-expiry", address)
                self.assertEqual(worker.recvfrom(4096)[0], b"after-expiry")

    def test_signed_exchange_reaches_real_profile_server(self):
        server = ProfileCommandServer("127.0.0.1", 0, "test-profile-token")
        result = {}
        try:
            with self.running_relay(server.socket.getsockname()) as address:
                def client():
                    result.update(send_request(address[0], address[1], "test-profile-token", "program_h", "nes", "Example.nes", 0.2))
                thread = threading.Thread(target=client); thread.start()
                deadline = time.monotonic() + 1
                request = None
                while request is None and time.monotonic() < deadline:
                    request = server.take(); time.sleep(0.005)
                self.assertIsNotNone(request)
                server.acknowledge(request, True, request.profile)
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertTrue(result["accepted"])
                self.assertEqual(result["profile"], "program_h")
        finally:
            server.close()


class HookTests(unittest.TestCase):
    def test_calibration_core_has_explicit_native_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Path(directory) / "404"
            process.mkdir()
            (process / "comm").write_text("retroarch\n")
            (process / "cmdline").write_bytes(
                b"retroarch\0-L\0/opt/retropie/libretrocores/lr-powerglove-dot/"
                b"powerglove_dot_libretro.so\0"
            )
            self.assertEqual(retropie_hook._running_retroarch_emulator(Path(directory)),
                             "lr-powerglove-dot")

    def test_running_core_detection_prefers_newest_retroarch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, core in (
                (101, "/opt/retropie/libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so"),
                (202, "/opt/retropie/libretrocores/lr-fceumm/fceumm_libretro.so"),
            ):
                process = root / str(pid)
                process.mkdir()
                (process / "comm").write_text("retroarch\n")
                (process / "cmdline").write_bytes(
                    b"retroarch\0-L\0" + core.encode() + b"\0game.nes\0"
                )
            self.assertEqual(
                retropie_hook._running_retroarch_emulator(root), "lr-fceumm"
            )

    def test_unknown_running_core_falls_back_to_joystick_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Path(directory) / "303"
            process.mkdir()
            (process / "comm").write_text("retroarch\n")
            (process / "cmdline").write_bytes(
                b"retroarch\0-L\0/tmp/unknown_libretro.so\0game.nes\0"
            )
            self.assertEqual(retropie_hook._running_retroarch_emulator(Path(directory)), "")

    def test_registered_game_starts_a_detached_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token"; token.write_text("test-profile-token")
            registry = root / "games.json"
            registry.write_text(json.dumps({"games": {"Example.nes": "program_h"}}))
            settings = root / "launcher.json"
            settings.write_text(json.dumps({
                "uno_q": "example.local", "token_file": str(token),
                "registry": str(registry),
            }))
            session_file = root / "state" / "active.json"
            output = io.StringIO()
            with patch("sys.argv", [
                "hook", "start", "nes", "lr-fceumm", "/roms/Example.nes", "retroarch",
                "--settings", str(settings), "--session-file", str(session_file),
            ]), patch.object(retropie_hook, "_start_session_process") as start, \
                    patch.object(retropie_hook, "send_request") as send, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(retropie_hook.main(), 0)
            start.assert_called_once()
            send.assert_not_called()
            self.assertTrue(retropie_hook._session_is_current(
                session_file, start.call_args[0][1]
            ))
            self.assertIn("program_h", output.getvalue())

    def test_session_renews_only_while_retroarch_and_marker_are_active(self):
        with tempfile.TemporaryDirectory() as directory:
            session_file = Path(directory) / "active.json"
            session_id = "c" * 32
            retropie_hook._write_session(session_file, session_id)
            args = SimpleNamespace(
                session_id=session_id, session_file=session_file,
                startup_wait=1.0, heartbeat_seconds=0.25, lease_seconds=6.0,
                system="nes", rom="Example.nes",
            )
            settings = {"uno_q": "example.local", "port": 55356, "timeout": 0.1}
            with patch.object(retropie_hook, "_retroarch_running", side_effect=[True, True, False]), \
                    patch.object(retropie_hook, "send_request", return_value={"accepted": True}) as send, \
                    patch.object(retropie_hook.time, "sleep"):
                self.assertEqual(
                    retropie_hook._run_session(
                        args, settings, "test-profile-token",
                        {"profile": "program_1", "rapid_a": False},
                    ), 0
                )
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args_list[0][1]["session_id"], session_id)
            self.assertEqual(send.call_args_list[0][1]["lease_seconds"], 6.0)
            self.assertEqual(send.call_args_list[0][1]["emulator"], "")
            self.assertIs(send.call_args_list[0][1]["rapid_a"], False)
            self.assertIsNone(send.call_args_list[1][0][3])
            self.assertFalse(session_file.exists())

    def test_rejection_is_not_reported_as_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "launcher.json"
            settings.write_text(json.dumps({"uno_q": "example.local", "token_file": "unused"}))
            for ack in ({"accepted": False, "profile": None}, {"accepted": True, "profile": "program_b"}):
                output = io.StringIO()
                with patch("sys.argv", ["hook", "end", "--settings", str(settings)]), patch.object(retropie_hook, "read_token", return_value="test-profile-token"), patch.object(retropie_hook, "send_request", return_value=ack), contextlib.redirect_stdout(output):
                    self.assertEqual(retropie_hook.main(), 0)
                self.assertIn("rejected", output.getvalue())
                self.assertNotIn("acknowledged", output.getvalue())

    def test_missing_settings_does_not_fail_game_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.argv", ["hook", "start", "--settings", str(Path(directory) / "missing")]), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(retropie_hook.main(), 0)
            self.assertIn("unavailable", output.getvalue())


class VisionControlTests(unittest.TestCase):
    def test_off_applies_during_blocked_camera_open(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from powerglove_vision import vision_app
        from powerglove_vision.profile_control import ProfileRequest

        blocked = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        sent = []
        capture = MagicMock()
        tracker = MagicMock()
        def wait_for_release():
            blocked.set()
            release.wait(2)
            finished.set()
            return MagicMock(), capture, tracker
        def take():
            if blocked.is_set() and not sent:
                sent.append(True)
                return ProfileRequest("off-test", None, "nes", "", ("127.0.0.1", 1))
            return None
        def update(state, **_kwargs):
            if sent and state.get("active_profile") == "off":
                raise KeyboardInterrupt
        server = MagicMock(); server.take.side_effect = take
        shared = MagicMock()
        shared.take_profile_request.return_value = None
        shared.take_practice_request.return_value = None
        shared.take_controller_request.return_value = None
        shared.take_calibration_request.return_value = False
        shared.update_status.side_effect = update
        args = SimpleNamespace(profile="program_h", no_matrix=True, controller_enabled=False,
                               token="test-profile-token", device_config=None, token_file=None, receiver="", port=55355,
                               profile_listen="127.0.0.1", profile_port=55356,
                               web_host="127.0.0.1", web_port=8089, config=None)
        try:
            with patch.object(vision_app, "build_parser") as parser, patch.object(vision_app, "load_calibration", return_value=None), patch.object(vision_app, "UnoQMatrix"), patch.object(vision_app, "UdpSender"), patch.object(vision_app, "ProfileCommandServer", return_value=server), patch.object(vision_app, "SharedDebugState", return_value=shared), patch.object(vision_app, "start_debug_server"), patch.object(vision_app.signal, "signal"), patch.object(vision_app, "_prepare_vision", side_effect=lambda _args: wait_for_release()):
                parser.return_value.parse_args.return_value = args
                started = time.monotonic()
                self.assertEqual(vision_app.main(), 0)
                self.assertLess(time.monotonic() - started, 1)
                self.assertTrue(sent)
                self.assertFalse(release.is_set())
        finally:
            release.set()
            self.assertTrue(finished.wait(1))
