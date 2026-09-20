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

from virtualglove.launchbox_hook import (
    launch_command, load_settings, native_core_ready, run_game,
)
from virtualglove.launchbox_runtime import service_commands
from virtualglove.retroarch_hotkeys import conflicts


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
            "retroarch_native_config": str(root / "retroarch-native.cfg"),
            "input_route": "network-retropad",
            "retroarch_remote_port": 55001,
            "uno_q": "controller.local",
        }

    def test_settings_require_current_input_route_and_dynamic_port(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "launcher.json"
            current = self.settings(Path(name))
            path.write_text(json.dumps(current))
            self.assertEqual(load_settings(path)["retroarch_remote_port"], 55001)
            for route, port in (("windows-keyboard", 55001),
                                ("network-retropad", 48000),
                                ("network-retropad", True)):
                invalid = dict(current, input_route=route, retroarch_remote_port=port)
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    load_settings(path)

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
        self.assertTrue(any(item.endswith("retroarch-native.cfg") for item in native))
        self.assertTrue(any(item.endswith("retroarch-nes.cfg") for item in standard))

    def test_missing_native_core_falls_back_to_fceumm_but_keeps_joystick_lease(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            (root / "games.json").write_text(json.dumps({"games": {
                "Super Glove Ball (USA).nes": "super_glove_ball"
            }}))
            (root / "token").write_text("0123456789abcdef")
            calls, launched = [], []
            process = FakeProcess()
            code = run_game(
                settings, root / "Super Glove Ball (USA).nes",
                popen=lambda command, env: launched.append(command) or process,
                request=lambda *args, **kwargs: calls.append((args, kwargs)) or {"accepted": True},
                sleep=lambda _seconds: None,
            )
        self.assertEqual(code, 0)
        self.assertIn("fceumm_libretro.dll", launched[0][2])
        self.assertEqual(calls[0][0][3], "super_glove_ball")
        self.assertEqual(calls[0][1]["emulator"], "lr-fceumm")

    def test_changed_native_core_hash_falls_back(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            settings["native_core_sha256"] = "0" * 64
            (root / "nestopia_powerglove_libretro.dll").write_bytes(b"changed")
            self.assertFalse(native_core_ready(settings))
            command, emulator = launch_command(
                settings, root / "Super Glove Ball (USA).nes",
                {"profile": "super_glove_ball"}, native_ready=False)
        self.assertIn("fceumm_libretro.dll", command[2])
        self.assertEqual(emulator, "lr-fceumm")

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

    def test_keyboard_hotkey_conflict_warns_but_retropad_remains_enabled(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            settings = self.settings(root)
            settings["retroarch_main_config"] = str(root / "retroarch.cfg")
            settings["retroarch_config"] = str(root / "retroarch-nes.cfg")
            settings["input_warning"] = str(root / "warning.txt")
            (root / "retroarch.cfg").write_text('input_exit_emulator = "x"\n')
            (root / "retroarch-nes.cfg").write_text('input_player1_a = "x"\n')
            (root / "games.json").write_text(json.dumps({"games": {
                "Super Mario Bros. (USA).nes": "program_12"
            }}))
            (root / "token").write_text("0123456789abcdef")
            launched, requested = [], []
            code = run_game(
                settings, root / "Super Mario Bros. (USA).nes",
                popen=lambda command, env: launched.append(command) or FakeProcess(),
                request=lambda *args, **kwargs: requested.append((args, kwargs)),
            )
            warning = (root / "warning.txt").read_text()
        self.assertEqual(code, 0)
        self.assertEqual(requested[0][0][3], "program_12")
        self.assertIn("fceumm_libretro.dll", launched[0][2])
        self.assertIn("Physical keyboard backup", warning)
        self.assertIn("input_exit_emulator uses x", warning)

    def test_hotkey_audit_ignores_intentional_player_and_gamepad_binds(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "retroarch.cfg"
            path.write_text('input_player1_a = "x"\ninput_enable_hotkey_btn = "12"\n')
            self.assertEqual(conflicts([path]), [])

    def test_hotkey_audit_rejects_other_player_and_unmanaged_player1_collisions(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "retroarch.cfg"
            path.write_text('input_player2_a = "x"\ninput_player1_y = "z"\n')
            found = conflicts([path])
        self.assertEqual([item["setting"] for item in found],
                         ["input_player2_a", "input_player1_y"])

    def test_hotkey_audit_reports_every_virtualglove_key_and_hotkey_enable(self):
        keys = ("up", "down", "left", "right", "x", "z", "enter", "rshift")
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "retroarch.cfg"
            path.write_text("\n".join(
                ('input_enable_hotkey' if index == 0 else 'input_command_%d' % index) +
                ' = "' + key + '"' for index, key in enumerate(keys)
            ) + "\n")
            found = conflicts([path])
        self.assertEqual([item["key"] for item in found], list(keys))
        self.assertEqual(found[0]["setting"], "input_enable_hotkey")

    def test_hotkey_audit_uses_effective_last_assignment_across_configs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            main = root / "retroarch.cfg"
            append = root / "nes.cfg"
            main.write_text('input_exit_emulator = "x"\ninput_menu_toggle = "escape"\n')
            append.write_text('input_exit_emulator = "escape"\ninput_menu_toggle = "z"\n')
            found = conflicts([main, append])
        self.assertEqual([(item["setting"], item["key"]) for item in found],
                         [("input_menu_toggle", "z")])

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

    def test_runtime_uses_loopback_retropad_and_shared_native_record(self):
        settings = self.settings(Path("C:/VirtualGlove"))
        settings["settings_path"] = "C:/VirtualGlove/data/launcher.json"
        receiver, games = service_commands(settings)
        self.assertIn("retroarch-remote", receiver)
        self.assertIn("--retroarch-port", receiver)
        self.assertIn("55001", receiver)
        self.assertIn(settings["native_state"], receiver)
        self.assertIn("virtualglove.game_registry", games)

    def test_desktop_append_config_disables_touch_overlay(self):
        config = (ROOT / "launchbox/retroarch-nes.cfg").read_text()
        self.assertIn('input_overlay = ""', config)
        self.assertIn('input_overlay_enable = "false"', config)
        self.assertIn('input_overlay_enable_autopreferred = "false"', config)
        self.assertIn('network_remote_enable = "true"', config)
        self.assertIn('network_remote_enable_user_p1 = "true"', config)
        native = (ROOT / "launchbox/retroarch-native.cfg").read_text()
        self.assertIn('network_remote_enable = "false"', native)
        self.assertIn('network_remote_enable_user_p1 = "false"', native)

    def test_receiver_import_does_not_require_the_linux_backend(self):
        real_import = builtins.__import__

        def without_fcntl(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("Windows has no fcntl")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=without_fcntl):
            import importlib
            receiver = importlib.import_module("virtualglove.receiver")
            importlib.reload(receiver)
        self.assertIn("retroarch-remote", receiver.build_parser()._option_string_actions[
            "--output-device"
        ].choices)

    def test_package_contains_non_destructive_per_user_installer_and_build_workflow(self):
        installer = (ROOT / "launchbox/install-launchbox.ps1").read_text()
        wrapper = (ROOT / "launchbox/virtualglove-launchbox.cmd").read_text()
        pairing = (ROOT / "launchbox/virtualglove-pair.ps1").read_text()
        restart = (ROOT / "launchbox/virtualglove-restart-runtime.cmd").read_text()
        configure = (ROOT / "launchbox/configure-launchbox-emulator.ps1").read_text()
        workflow = (ROOT / ".github/workflows/launchbox-native-core.yml").read_text()
        build_script = (ROOT / "scripts/build-launchbox-nestopia-powerglove.sh").read_text()
        self.assertIn("LOCALAPPDATA", installer)
        self.assertIn('PSBoundParameters.ContainsKey("ControllerHost")', installer)
        self.assertIn('ControllerHost = "virtualglove.local"', installer)
        self.assertIn("UTF8Encoding($false)", installer)
        self.assertNotIn("Set-Content -Encoding UTF8 $Settings", installer)
        self.assertNotIn("Register-ScheduledTask", installer)
        self.assertIn("New-NetFirewallRule", installer)
        self.assertIn("LocalSubnet", installer)
        self.assertIn("network-retropad", installer)
        self.assertIn("retroarch_remote_port", installer)
        self.assertIn("--check-loopback", installer)
        self.assertIn("Test-RetroPadPortAvailable", installer)
        self.assertIn("ExclusiveAddressUse", installer)
        self.assertIn("[Net.IPAddress]::Loopback", installer)
        self.assertIn("retroarch-native.cfg", installer)
        self.assertIn("WindowsBuiltInRole]::Administrator", installer)
        self.assertIn("nestopia-powerglove-source.tar.gz", installer)
        self.assertIn("Get-FileHash", installer)
        self.assertIn("--load", installer)
        self.assertIn("native_core_sha256", installer)
        self.assertIn("source_sha256", installer)
        self.assertIn("launchbox_runtime ensure", wrapper)
        self.assertIn("virtualglove-restart-runtime.cmd", installer)
        self.assertIn("--receiver-restart-command $Restart", pairing)
        self.assertNotIn("--receiver-restart-command $Python -m", pairing)
        self.assertIn("launchbox_runtime restart", restart)
        self.assertIn("LaunchBox-Emulators.xml", configure)
        self.assertIn("LaunchBox-Nintendo-Entertainment-System.xml", configure)
        self.assertIn("Nintendo Entertainment System", configure)
        self.assertIn("VirtualGlove RetroArch", configure)
        self.assertIn("$virtualGlove.ApplicationPath = $PythonPath", configure)
        self.assertIn("virtualglove.launchbox_hook", configure)
        self.assertIn("$game.Emulator = $emulatorId", configure)
        self.assertIn("[string]$_.Emulator -eq [string]$retroArch[0].ID", configure)
        self.assertIn("the backup was restored", configure)
        self.assertIn("configure-launchbox-emulator.ps1", installer)
        self.assertIn("-PythonPath $Python -SettingsPath $Settings", installer)
        self.assertIn("Close LaunchBox, Big Box, and RetroArch", installer)
        self.assertIn("Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue", installer)
        self.assertIn("$QuietScans -lt 4", installer)
        self.assertIn("$RemainingServices.Count -gt 0", installer)
        self.assertIn("(virtualglove|$LegacyModule)\\.(launchbox_runtime|receiver|game_registry)", installer)
        self.assertIn('-m pip uninstall --disable-pip-version-check -y $LegacyDistribution', installer)
        self.assertIn('$LegacyModuleRoot = Join-Path $RuntimeRoot "Lib\\site-packages\\$LegacyModule"', installer)
        self.assertIn('Remove-Item -LiteralPath $LegacyModuleRoot -Recurse -Force', installer)
        self.assertIn('-Filter "$LegacyCommands*"', installer)
        self.assertIn('$RetiredRuntime.Count -gt 0', installer)
        retired_distribution = 'power' + 'glove-vision'
        retired_module = 'power' + 'glove_vision'
        self.assertNotIn(retired_distribution, installer)
        self.assertNotIn(retired_module, installer)
        hook = (ROOT / "src/virtualglove/launchbox_hook.py").read_text()
        self.assertIn("ensure_background(args.settings)", hook)
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
        self.assertIn("GetEnvironmentVariableW", windows_patch)
        self.assertIn('library_name     = "Nestopia VirtualGlove"', windows_patch)
        self.assertIn("Core::Input::Controllers::PowerGlove::START", windows_patch)
        self.assertIn("RETRO_DEVICE_ID_JOYPAD_START", windows_patch)
        self.assertIn("RETRO_DEVICE_ID_JOYPAD_SELECT", windows_patch)
        self.assertNotIn("QueryPerformanceCounter", base_patch)


if __name__ == "__main__":
    unittest.main()
