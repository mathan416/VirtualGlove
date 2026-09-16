# Project: VirtualGlove
# File: tests/test_launchbox.py
# Purpose: Verify LaunchBox core selection, leases, and packaging assets.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added LaunchBox integration and packaging coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the Windows x86-64 LaunchBox integration."""

import json
import builtins
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from powerglove_vision.launchbox_hook import launch_command, run_game
from powerglove_vision.launchbox_runtime import service_commands


ROOT = Path(__file__).resolve().parents[1]


class FakeProcess:
    def __init__(self, result=0):
        self.result = result
        self.polls = 0
        self.terminated = False

    def poll(self):
        self.polls += 1
        return None if self.polls == 1 else self.result

    def wait(self):
        return self.result

    def terminate(self):
        self.terminated = True


class LaunchBoxTests(unittest.TestCase):
    def settings(self, root):
        return {
            "retroarch": str(root / "retroarch.exe"),
            "fceumm_core": str(root / "fceumm_libretro.dll"),
            "native_core": str(root / "nestopia_powerglove_libretro.dll"),
            "registry": str(root / "games.json"),
            "token_file": str(root / "token"),
            "native_state": str(root / "native-state.bin"),
            "retroarch_config": str(root / "retroarch-nes.cfg"),
            "uno_q": "controller.local",
        }

    def test_only_super_glove_ball_selects_the_native_core(self):
        settings = self.settings(Path("C:/VirtualGlove"))
        native, native_name = launch_command(
            settings, Path("Super Glove Ball (USA).nes"), {"profile": "super_glove_ball"}
        )
        standard, standard_name = launch_command(
            settings, Path("Super Mario Bros. (USA).nes"), {"profile": "program_12"}
        )
        self.assertIn("nestopia_powerglove_libretro.dll", native[2])
        self.assertEqual(native_name, "lr-nestopia-powerglove")
        self.assertIn("fceumm_libretro.dll", standard[2])
        self.assertEqual(standard_name, "lr-fceumm")
        self.assertEqual(native[-1], "Super Glove Ball (USA).nes")

    def test_registered_game_renews_and_clears_authenticated_lease(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            (root / "games.json").write_text(json.dumps({"games": {
                "Super Mario Bros. (USA).nes": {
                    "profile": "program_12", "rapid_a": False
                }
            }}))
            (root / "token").write_text("0123456789abcdef")
            calls = []
            process = FakeProcess()
            code = run_game(
                settings, root / "Super Mario Bros. (USA).nes",
                popen=lambda command, env: process,
                request=lambda *args, **kwargs: calls.append((args, kwargs)) or {"accepted": True},
                sleep=lambda _seconds: None,
            )
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0][3], "program_12")
        self.assertEqual(calls[0][1]["emulator"], "lr-fceumm")
        self.assertFalse(calls[0][1]["rapid_a"])
        self.assertIsNone(calls[-1][0][3])

    def test_unregistered_game_uses_fceumm_without_enabling_gestures(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            (root / "games.json").write_text('{"games":{}}')
            launched = []
            requested = []
            code = run_game(
                settings, root / "Homebrew.nes",
                popen=lambda command, env: launched.append((command, env)) or FakeProcess(),
                request=lambda *args, **kwargs: requested.append((args, kwargs)),
            )
        self.assertEqual(code, 0)
        self.assertIn("fceumm_libretro.dll", launched[0][0][2])
        self.assertEqual(requested, [])
        self.assertEqual(launched[0][1]["VIRTUALGLOVE_NATIVE_STATE"], settings["native_state"])

    def test_registered_game_still_launches_before_pairing(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            (root / "games.json").write_text(json.dumps({"games": {
                "Super Mario Bros. (USA).nes": "program_12"
            }}))
            launched = []
            requested = []
            code = run_game(
                settings, root / "Super Mario Bros. (USA).nes",
                popen=lambda command, env: launched.append(command) or FakeProcess(),
                request=lambda *args, **kwargs: requested.append((args, kwargs)),
            )
        self.assertEqual(code, 0)
        self.assertIn("fceumm_libretro.dll", launched[0][2])
        self.assertEqual(requested, [])

    def test_missing_registry_fails_open_to_fceumm(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            launched = []
            code = run_game(
                settings, root / "Super Mario Bros. (USA).nes",
                popen=lambda command, env: launched.append(command) or FakeProcess(),
            )
        self.assertEqual(code, 0)
        self.assertIn("fceumm_libretro.dll", launched[0][2])

    def test_runtime_uses_windows_keyboard_and_shared_native_record(self):
        settings = self.settings(Path("C:/VirtualGlove"))
        settings["settings_path"] = "C:/VirtualGlove/data/launcher.json"
        receiver, games = service_commands(settings)
        self.assertIn("windows-keyboard", receiver)
        self.assertIn(settings["native_state"], receiver)
        self.assertIn("powerglove_vision.game_registry", games)

    def test_receiver_import_does_not_require_the_linux_backend(self):
        real_import = builtins.__import__

        def without_fcntl(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("Windows has no fcntl")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=without_fcntl):
            import importlib
            receiver = importlib.import_module("powerglove_vision.receiver")
            importlib.reload(receiver)
        self.assertIn("windows-keyboard", receiver.build_parser()._option_string_actions[
            "--output-device"
        ].choices)

    def test_package_contains_non_destructive_per_user_installer_and_build_workflow(self):
        installer = (ROOT / "launchbox/install-launchbox.ps1").read_text()
        wrapper = (ROOT / "launchbox/virtualglove-launchbox.cmd").read_text()
        workflow = (ROOT / ".github/workflows/launchbox-native-core.yml").read_text()
        build_script = (ROOT / "scripts/build-launchbox-nestopia-powerglove.sh").read_text()
        self.assertIn("LOCALAPPDATA", installer)
        self.assertIn('PSBoundParameters.ContainsKey("ControllerHost")', installer)
        self.assertIn('ControllerHost = "virtualglove.local"', installer)
        self.assertIn("UTF8Encoding($false)", installer)
        self.assertNotIn("Set-Content -Encoding UTF8 $Settings", installer)
        self.assertNotIn("Register-ScheduledTask", installer)
        self.assertNotIn("New-NetFirewallRule", installer)
        self.assertIn("nestopia-powerglove-source.tar.gz", installer)
        self.assertIn("Get-FileHash", installer)
        self.assertIn("source_sha256", installer)
        self.assertIn("launchbox_runtime ensure", wrapper)
        self.assertIn("windows-latest", workflow)
        self.assertIn("nestopia_powerglove_libretro.dll", workflow)
        self.assertIn("nestopia-powerglove-source.tar.gz", workflow)
        self.assertIn("libwinpthread", build_script)
        self.assertIn("unbundled MinGW runtime DLL", build_script)

    def test_windows_portability_patch_does_not_change_linux_base_patch(self):
        windows_patch = (ROOT / "native/launchbox/nestopia-windows.patch").read_text()
        base_patch = (ROOT / "native/nestopia-powerglove/nestopia-powerglove.patch").read_text()
        self.assertIn("#ifdef _WIN32", windows_patch)
        self.assertIn("QueryPerformanceCounter", windows_patch)
        self.assertIn("CreateFileW", windows_patch)
        self.assertIn("CreateFileMappingA", windows_patch)
        self.assertNotIn("QueryPerformanceCounter", base_patch)


if __name__ == "__main__":
    unittest.main()
