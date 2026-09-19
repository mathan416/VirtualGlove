# Project: VirtualGlove
# File: tests/test_controller_router.py
# Purpose: Verify multi-player routing, migration, authentication, and safety.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added Controller Router coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify Controller Router configuration, arbitration, and paired operations."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from virtualglove import controller_router as router
from virtualglove.controller_router_web import ROUTER_CONTENT, ROUTER_SCRIPT
from virtualglove.profile_control import sign_message, verify_message
from virtualglove.retropie_hook import configure_four_score
from virtualglove.setup_web import SETUP_CONTENT, SETUP_SCRIPT


MAPPING = [{"name": "a", "type": "button", "code": 0, "value": 1}]


def source(identity="pad-one", name="Pad"):
    return {"id": identity, "name": name, "guid": "guid", "vendor": "1234",
            "product": "5678", "version": "0100", "uniq": identity,
            "phys": "", "mapping": list(MAPPING)}


class ControllerRouterTests(unittest.TestCase):
    def test_setup_reload_event_prevents_false_unpaired_message(self):
        self.assertIn("dispatchEvent(new Event('virtualglove-config-loaded'))", SETUP_SCRIPT)
        self.assertIn("addEventListener('virtualglove-config-loaded',load)", ROUTER_SCRIPT)
        self.assertNotIn("Choose and pair a supported console first", ROUTER_CONTENT + ROUTER_SCRIPT)

    def test_setup_places_router_in_its_own_card_before_pairing(self):
        connection = SETUP_CONTENT.index('id=connection-section')
        controller_router = SETUP_CONTENT.index('id=controller-router')
        pairing = SETUP_CONTENT.index('id=pairing-card')
        doctor = SETUP_CONTENT.index('id=connection-doctor')
        self.assertLess(connection, controller_router)
        self.assertLess(controller_router, pairing)
        self.assertLess(pairing, doctor)
        self.assertIn('<section id=controller-router class=card', SETUP_CONTENT)
        self.assertNotIn('id=pairing-section class=connection-pairing', SETUP_CONTENT)

    def test_config_supports_four_slots_and_rejects_duplicate_source(self):
        data = router.validate_config({"format": 2, "platform": "batocera",
            "players": [{"player": 1, "sources": [source()]},
                        {"player": 4, "sources": [source("pad-four")]}],
            "virtualglove_player": 3})
        self.assertEqual(router.enabled_players(data), [1, 3, 4])
        with self.assertRaisesRegex(ValueError, "multiple players"):
            router.validate_config({"format": 2, "platform": "batocera",
                "players": [{"player": 1, "sources": [source()]},
                            {"player": 2, "sources": [source()]}],
                "virtualglove_player": None})
        with self.assertRaisesRegex(ValueError, "must be unassigned"):
            router.validate_config({"format": 2, "platform": "batocera",
                                    "players": [], "virtualglove_player": True})

    def test_v1_migration_preserves_identity_mapping_and_virtual_player(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / "player1-controller.json", Path(directory) / "controller-router.json"
            old.write_text(json.dumps({"format": 1, "platform": "recalbox", **source()}))
            result = router.migrate_player1(old, new, "recalbox")
            self.assertEqual(result["players"][0]["sources"][0]["id"], "pad-one")
            self.assertEqual(result["virtualglove_player"], 1)
            self.assertTrue(old.exists())

    def test_inventory_deduplicates_repeated_emulationstation_entry(self):
        duplicate = {**source(), "event": "/dev/input/event1", "joystick": "/dev/input/js1"}
        with patch.object(router, "controller_candidates", return_value=[duplicate, duplicate]):
            result = router.inventory(Path("/unused"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["suggested_player"], 1)

    def test_inventory_keeps_two_interfaces_from_one_ipac_board(self):
        first = {**source("ipac-input0", "Ultimarc I-PAC Ultimate I/O"),
                 "uniq": "5", "phys": "usb-1/input0",
                 "event": "/dev/input/event0", "joystick": "/dev/input/js0"}
        second = {**source("ipac-input2", "Ultimarc I-PAC Ultimate I/O"),
                  "uniq": "5", "phys": "usb-1/input2",
                  "event": "/dev/input/event4", "joystick": "/dev/input/js1"}
        with patch.object(router, "controller_candidates", return_value=[first, second]):
            result = router.inventory(Path("/unused"))
        self.assertEqual([item["id"] for item in result],
                         ["ipac-input0", "ipac-input2"])
        self.assertEqual([item["suggested_player"] for item in result], [1, 2])

    def test_latest_active_physical_axis_wins_then_resumes_and_beats_glove(self):
        state = router.PlayerState(1); state.active = True
        first, second = router.SourceState(), router.SourceState()
        state.physical = {"first": first, "second": second}
        state.virtual.set_axis("hat_x", -1, 1)
        first.set_axis("hat_x", 1, 2); second.set_axis("hat_x", -1, 3)
        self.assertEqual(state.desired()[1]["hat_x"], -1)
        second.set_axis("hat_x", 0, 4)
        self.assertEqual(state.desired()[1]["hat_x"], 1)
        state.virtual.set_axis("hat_y", 1, 4)
        self.assertEqual(state.desired()[1]["hat_y"], 0)
        first.set_axis("hat_x", 0, 5)
        self.assertEqual(state.desired()[1]["hat_x"], -1)
        self.assertEqual(state.desired()[1]["hat_y"], 1)

    def test_buttons_merge_and_only_player1_may_carry_physical_hotkey(self):
        p1, p2 = router.PlayerState(1), router.PlayerState(2)
        for state in (p1, p2):
            state.active = True; physical = router.SourceState(); physical.buttons = {"a", "hotkey"}
            state.physical["pad"] = physical; state.virtual.buttons = {"b", "select"}
        self.assertEqual(p1.desired()[0], {"a", "b", "select", "hotkey"})
        self.assertEqual(p2.desired()[0], {"a", "b", "select"})

    def test_retroarch_block_manages_enabled_players_without_unrelated_changes(self):
        config = router.validate_config({"format": 2, "platform": "batocera",
            "players": [{"player": 1, "sources": [source()]}, {"player": 2, "sources": []}],
            "virtualglove_player": 2})
        text = router.merge_retroarch_config('video_driver = "gl"\ninput_player3_joypad_index = "8"\n',
                                             config, {1: 4, 2: 5})
        self.assertIn('input_player1_joypad_index = "4"', text)
        self.assertIn('input_player2_joypad_index = "5"', text)
        self.assertIn('input_player3_joypad_index = "8"', text)
        self.assertEqual(text.count("input_enable_hotkey_btn"), 1)

    def test_store_rejects_stale_updates_and_changes_during_fceumm(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); es = base / "es.xml"; es.write_text("<inputList/>")
            store = router.RouterStore(base / "router.json", "recalbox", es,
                                       activity_check=lambda: False)
            with patch.object(router, "controller_candidates", return_value=[source()]):
                current = store.read()
                saved = store.operate("save", {"revision": current["revision"],
                    "config": {"players": [{"player": 1, "sources": ["pad-one"]}],
                               "virtualglove_player": 1}})
                with self.assertRaisesRegex(ValueError, "changed elsewhere"):
                    store.operate("save", {"revision": current["revision"], "config": {}})
                self.assertEqual(saved["config"]["players"][0]["sources"][0]["id"], "pad-one")
            blocked = router.RouterStore(base / "router.json", "recalbox", es,
                                         activity_check=lambda: True)
            with self.assertRaisesRegex(ValueError, "Close the running"):
                blocked.operate("rollback", {"revision": blocked.read()["revision"]})

    def test_failed_first_activation_removes_new_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); es = base / "es.xml"; es.write_text("<inputList/>")
            path = base / "router.json"
            store = router.RouterStore(path, "retropie", es,
                activity_check=lambda: False,
                activate=lambda: (_ for _ in ()).throw(RuntimeError("service failed")))
            with patch.object(router, "controller_candidates", return_value=[source()]):
                current = store.read()
                with self.assertRaisesRegex(ValueError, "previous configuration was restored"):
                    store.operate("save", {"revision": current["revision"],
                        "config": {"players": [{"player": 1, "sources": ["pad-one"]}],
                                   "virtualglove_player": 1}})
            self.assertFalse(path.exists())

    def test_store_rejects_malformed_public_player_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); es = base / "es.xml"; es.write_text("<inputList/>")
            store = router.RouterStore(base / "router.json", "recalbox", es,
                                       activity_check=lambda: False)
            current = store.read()
            for malformed in ("not-a-list", ["not-an-object"],
                              [{"player": 1, "sources": [], "extra": True}]):
                with self.assertRaises(ValueError):
                    store.operate("save", {"revision": current["revision"],
                                           "config": {"players": malformed,
                                                      "virtualglove_player": None}})

    def test_failed_grab_drops_only_the_unavailable_source(self):
        device = router.ControllerRouterDevice.__new__(router.ControllerRouterDevice)
        device.players = {1: router.PlayerState(1)}
        source_state = router.SourceState()
        device.players[1].physical["pad"] = source_state
        device.descriptors = {7: {"fd": 7, "source_id": "pad", "player": 1,
                                  "source": source_state, "mapper": None,
                                  "grabbed": False}}
        device.sinks = {1: Mock()}
        with patch.object(router.fcntl, "ioctl", side_effect=OSError), \
                patch.object(router.os, "close"):
            device._set_active(True)
        self.assertEqual(device.descriptors, {})
        self.assertTrue(device.players[1].active)
        device.sinks[1].write.assert_called()

    def test_fceumm_detection_requires_the_fceumm_core(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory); (proc / "10").mkdir(); (proc / "11").mkdir()
            (proc / "10/cmdline").write_bytes(b"retroarch\0-L\0/usr/lib/libretro/nestopia_libretro.so\0")
            self.assertFalse(router.fceumm_running(proc))
            (proc / "11/cmdline").write_bytes(b"retroarch\0-L\0/usr/lib/libretro/fceumm_libretro.so\0")
            self.assertTrue(router.fceumm_running(proc))

    def test_inputs_protocol_authenticates_and_rejects_replay(self):
        class Store:
            def operate(self, operation, payload):
                return {"operation": operation}
        with tempfile.TemporaryDirectory() as directory:
            token = "controller-router-test-token"
            token_file = Path(directory) / "token"; token_file.write_text(token)
            service = router.RouterService(Store(), token_file, clock=lambda: 10)
            challenge = service.exchange({"protocol": router.PROTOCOL,
                "operation": "challenge", "request_id": "request"})["challenge"]
            request = sign_message({"protocol": router.PROTOCOL, "operation": "read",
                "request_id": "request", "challenge": challenge}, token)
            response = service.exchange(request)
            self.assertTrue(response["ok"]); self.assertTrue(verify_message(response, token))
            with self.assertRaisesRegex(ValueError, "Expired or already used"):
                service.exchange(request)

    def test_four_score_force_is_bounded_and_auto_removes_managed_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nes.cfg"
            path.write_text('video_driver = "gl"\n')
            settings = {"controller_router": {"retroarch_config": str(path)}}
            configure_four_score(settings, True)
            self.assertIn('input_libretro_device_p5 = "769"', path.read_text())
            configure_four_score(settings, False)
            self.assertNotIn("input_libretro_device_p5", path.read_text())
            self.assertIn('video_driver = "gl"', path.read_text())

    def test_terminal_wizard_assigns_physical_and_virtual_players(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); es = base / "es.xml"; es.write_text("<inputList/>")
            activated, output = Mock(), []
            store = router.RouterStore(base / "router.json", "batocera", es,
                                       activity_check=lambda: False, activate=activated)
            answers = iter(("1", "2", "v", "3", "s", "y"))
            with patch.object(router, "controller_candidates", return_value=[source()]):
                self.assertEqual(router.run_setup_wizard(
                    store, input_fn=lambda _prompt: next(answers), output_fn=output.append,
                    verify_fn=lambda _config: True), 0)
                saved = router.load_config(base / "router.json")
            self.assertEqual(saved["players"][0]["player"], 2)
            self.assertEqual(saved["virtualglove_player"], 3)
            activated.assert_called_once_with()
            self.assertTrue(any("outputs verified" in line for line in output))

    def test_terminal_wizard_quit_does_not_write_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); es = base / "es.xml"; es.write_text("<inputList/>")
            store = router.RouterStore(base / "router.json", "recalbox", es,
                                       activity_check=lambda: False)
            with patch.object(router, "controller_candidates", return_value=[source()]):
                router.run_setup_wizard(store, input_fn=lambda _prompt: "q",
                                        output_fn=lambda _line: None)
            self.assertFalse((base / "router.json").exists())

    def test_platform_detection_uses_console_markers(self):
        def is_file(path):
            return str(path) == "/usr/share/batocera/batocera.version"
        with patch.object(Path, "is_file", is_file), patch.object(Path, "is_dir", return_value=False):
            self.assertEqual(router.detect_platform(), "batocera")


if __name__ == "__main__":
    unittest.main()
