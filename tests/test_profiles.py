# Project: VirtualGlove
# File: tests/test_profiles.py
# Purpose: Verify authenticated profile commands, game matching, acknowledgements, and rejection paths.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Cover authenticated reverse discovery and cached profile delivery.
#   2026-09-05 - Covered renewable game-session validation and expiry.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify authenticated profile commands, game matching, acknowledgements, and rejection paths."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from virtualglove.profile_control import (
    ActiveGameLease,
    load_registry,
    select_profile_settings,
    sign_message,
    send_request,
    verify_message,
    ProfileCommandServer,
    ProfileRequest,
)
from virtualglove.vision_app import _consume_game_lease, _controller_context_active


class ProfileTests(unittest.TestCase):
    def test_signature_detects_tampering(self):
        message = sign_message({"protocol": "virtualglove-profile/1", "profile": "program_b"}, "a-long-test-token")
        self.assertTrue(verify_message(message, "a-long-test-token"))
        message["profile"] = "program_g"
        self.assertFalse(verify_message(message, "a-long-test-token"))

    def test_registry_uses_exact_case_insensitive_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            path.write_text(json.dumps({"games": {"Joust (USA).nes": "program_b"}}))
            registry = load_registry(path)
        self.assertEqual(select_profile_settings(registry, "nes", "/roms/JOUST (USA).NES"),
                         {"profile": "program_b"})
        self.assertIsNone(select_profile_settings(registry, "snes", "/roms/JOUST (USA).NES"))
        self.assertIsNone(select_profile_settings(registry, "nes", "/roms/Other.nes"))

    def test_registry_rejects_unknown_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            path.write_text(json.dumps({"games": {"Mystery.nes": "run-a-command"}}))
            with self.assertRaises(ValueError):
                load_registry(path)

    def test_structured_registry_preserves_rapid_fire_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            path.write_text(json.dumps({"games": {
                "Blaster Master (USA).nes": {
                    "profile": "program_1", "rapid_a": False,
                }
            }}))
            registry = load_registry(path)
        self.assertEqual(
            select_profile_settings(registry, "nes", "Blaster Master (USA).nes"),
            {"profile": "program_1", "rapid_a": False},
        )

    def test_structured_registry_rejects_unknown_or_non_boolean_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            for value in (
                {"profile": "program_1", "rapid_a": 0},
                {"profile": "program_1", "extra": False},
                {"rapid_a": False},
            ):
                path.write_text(json.dumps({"games": {"Example.nes": value}}))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_registry(path)

    def test_request_is_acknowledged_while_worker_is_busy(self):
        server = ProfileCommandServer("127.0.0.1", 0, "a-long-test-token")
        try:
            # No worker consumes the queue while the caller waits for its reply.
            ack = send_request("127.0.0.1", server.socket.getsockname()[1],
                               "a-long-test-token", "program_h", "nes", "Example.7z", 0.2)
            self.assertTrue(ack["accepted"])
            self.assertTrue(ack["queued"])
            self.assertEqual(server.take().profile, "program_h")
        finally:
            server.close()

    def test_renewable_game_request_carries_a_bounded_lease(self):
        server = ProfileCommandServer("127.0.0.1", 0, "a-long-test-token")
        try:
            ack = send_request(
                "127.0.0.1", server.socket.getsockname()[1],
                "a-long-test-token", "program_h", "nes", "Example.7z", 0.2,
                session_id="a" * 32, lease_seconds=6.0, emulator="lr-fceumm",
                rapid_a=False, rapid_b=True,
            )
            self.assertTrue(ack["accepted"])
            request = server.take()
            self.assertEqual(request.session_id, "a" * 32)
            self.assertEqual(request.lease_seconds, 6.0)
            self.assertEqual(request.emulator, "lr-fceumm")
            self.assertIs(request.rapid_a, False)
            self.assertIs(request.rapid_b, True)
        finally:
            server.close()

    def test_stale_controller_address_discovers_and_caches_authenticated_peer(self):
        token = "profile-discovery-test-token"
        server = ProfileCommandServer("127.0.0.1", 0, token)
        port = server.socket.getsockname()[1]
        try:
            ack = send_request(
                "127.0.0.2", port, token, "program_h", "nes", "Example.7z", 0.05,
                discovery_addresses=lambda: ("127.0.0.1",),
            )
            self.assertTrue(ack["accepted"])
            self.assertEqual(server.take().profile, "program_h")

            def discovery_must_not_run():
                raise AssertionError("authenticated address cache was not used")

            ack = send_request(
                "127.0.0.2", port, token, "program_g", "nes", "Second.7z", 0.05,
                discovery_addresses=discovery_must_not_run,
            )
            self.assertTrue(ack["accepted"])
            self.assertEqual(server.take().profile, "program_g")
        finally:
            server.close()

    def test_discovery_never_accepts_a_controller_with_the_wrong_pairing_key(self):
        server = ProfileCommandServer("127.0.0.1", 0, "correct-profile-token")
        try:
            with self.assertRaises(TimeoutError):
                send_request(
                    "127.0.0.2", server.socket.getsockname()[1],
                    "different-profile-token", "program_h", "nes", "Example.7z", 0.03,
                    discovery_addresses=lambda: ("127.0.0.1",),
                )
            self.assertIsNone(server.take())
        finally:
            server.close()

    def test_game_lease_refresh_does_not_repeat_a_transition(self):
        lease = ActiveGameLease()
        request = ProfileRequest(
            "one", "program_h", "nes", "Example.7z", ("127.0.0.1", 1),
            session_id="b" * 32, lease_seconds=6.0,
        )
        self.assertTrue(lease.refresh(request, 10.0))
        self.assertFalse(lease.refresh(request, 12.0))
        self.assertFalse(lease.expire(17.9))
        self.assertTrue(lease.expire(18.0))
        self.assertFalse(lease.snapshot(18.0)["game_session_active"])

    def test_rapid_fire_change_is_a_game_lease_transition(self):
        lease = ActiveGameLease()
        first = ProfileRequest(
            "one", "program_1", "nes", "Example.nes", ("127.0.0.1", 1),
            session_id="r" * 32, lease_seconds=6.0, rapid_a=False,
        )
        changed = ProfileRequest(
            "two", "program_1", "nes", "Example.nes", ("127.0.0.1", 1),
            session_id="r" * 32, lease_seconds=6.0, rapid_a=True,
        )
        self.assertTrue(lease.refresh(first, 10.0))
        self.assertFalse(lease.refresh(first, 11.0))
        self.assertTrue(lease.refresh(changed, 12.0))

    def test_request_carries_emulator_and_core_change_is_a_transition(self):
        lease = ActiveGameLease()
        native = ProfileRequest(
            "one", "super_glove_ball", "nes", "Super Glove Ball.7z",
            ("127.0.0.1", 1), emulator="lr-nestopia-powerglove",
            session_id="e" * 32, lease_seconds=6.0,
        )
        joystick = ProfileRequest(
            "two", "super_glove_ball", "nes", "Super Glove Ball.7z",
            ("127.0.0.1", 1), emulator="lr-fceumm",
            session_id="e" * 32, lease_seconds=6.0,
        )
        self.assertTrue(lease.refresh(native, 10.0))
        self.assertFalse(lease.refresh(native, 11.0))
        self.assertTrue(lease.refresh(joystick, 12.0))
        self.assertEqual(lease.emulator, "lr-fceumm")

    def test_vision_consumes_heartbeats_once_and_turns_off_after_expiry(self):
        lease = ActiveGameLease()
        request = ProfileRequest(
            "one", "program_h", "nes", "Example.7z", ("127.0.0.1", 1),
            session_id="d" * 32, lease_seconds=6.0,
        )
        transition, expired = _consume_game_lease(request, lease, 10.0)
        self.assertIs(transition, request)
        self.assertFalse(expired)
        transition, expired = _consume_game_lease(request, lease, 12.0)
        self.assertIsNone(transition)
        self.assertFalse(expired)
        transition, expired = _consume_game_lease(None, lease, 18.0)
        self.assertIsNone(transition)
        self.assertTrue(expired)

    def test_controller_output_requires_a_game_or_manual_context(self):
        lease = ActiveGameLease()
        self.assertFalse(_controller_context_active(lease, "startup"))
        self.assertFalse(_controller_context_active(lease, "RetroPie game session expired"))
        self.assertTrue(_controller_context_active(lease, "Dashboard"))
        self.assertTrue(_controller_context_active(lease, "RetroPie launch hook"))
        lease.refresh(ProfileRequest(
            "one", "program_h", "nes", "Example.7z", ("127.0.0.1", 1),
            session_id="e" * 32, lease_seconds=6.0,
        ), 10.0)
        self.assertTrue(_controller_context_active(lease, "startup"))

    def test_shipped_registry_covers_archive_names(self):
        registry = load_registry(Path(__file__).resolve().parents[1] / "config/games.json")
        for name, expected in (("Joust (USA)", "program_b"),
                               ("Gyruss (USA)", "program_c"),
                               ("Sesame Street 123 (USA)", "program_f"),
                               ("Super Mario Bros. (Europe) (Rev A)", "program_12")):
            for extension in (".nes", ".zip", ".7z"):
                settings = select_profile_settings(registry, "nes", name + extension)
                self.assertEqual(settings["profile"] if settings else None, expected)

    def test_shipped_registry_covers_collection_aliases_and_combo_carts(self):
        registry = load_registry(Path(__file__).resolve().parents[1] / "config/games.json")
        expected = {
            "Legend of Zelda II, The - The Adventure of Link (USA).7z": "program_1",
            "Life Force - Salamander (Europe).zip": "program_5",
            "Xevious - The Avenger (USA).7z": "program_5",
            "Sesame Street ABC & 123 (USA).7z": "program_f",
            "Super Mario Bros. + Duck Hunt (USA).7z": "program_12",
            "Super Mario Bros. + Duck Hunt + World Class Track Meet (USA) (Rev A).7z": "program_12",
            "Super Mario Bros. + Tetris + Nintendo World Cup (Europe) (Rev A).7z": "program_12",
        }
        for name, profile in expected.items():
            settings = select_profile_settings(registry, "nes", name)
            self.assertEqual(settings["profile"] if settings else None, profile)

        blaster = select_profile_settings(registry, "nes", "Blaster Master (Europe).zip")
        self.assertEqual(blaster, {"profile": "program_1", "rapid_a": False})
        racket = select_profile_settings(registry, "nes", "Racket Attack (Europe).zip")
        self.assertEqual(racket, {"profile": "program_1", "rapid_a": False, "rapid_b": False})

    def test_command_server_acknowledges_profile(self):
        token = "a-long-test-token"
        server = ProfileCommandServer("127.0.0.1", 0, token)
        port = server.socket.getsockname()[1]
        result = {}

        def client():
            result.update(send_request(
                "127.0.0.1", port, token, "program_g", "nes",
                "/roms/Gun.Smoke (USA).nes", 0.2,
            ))

        thread = threading.Thread(target=client)
        thread.start()
        request = None
        deadline = time.monotonic() + 1
        while request is None and time.monotonic() < deadline:
            request = server.take()
            time.sleep(0.005)
        self.assertIsNotNone(request)
        server.acknowledge(request, True, request.profile)
        thread.join(timeout=1)
        server.close()
        self.assertFalse(thread.is_alive())
        self.assertTrue(result["accepted"])
        self.assertEqual(result["profile"], "program_g")


if __name__ == "__main__":
    unittest.main()
