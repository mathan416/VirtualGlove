# Project: VirtualGlove
# File: tests/test_setup_machine.py
# Purpose: Verify installer preservation, backups, hook integration and repeatability.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Verified the virtualglove Compose project-name migration.
#   2026-09-11 - Verified that the host identity reaches the containerized website.
#   2026-09-03 - Added isolated filesystem installation tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise installation without changing the host OS or invoking apt/systemd."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_machine", ROOT / "scripts/setup-machine.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
compose_spec = importlib.util.spec_from_file_location(
    "configure_uno_q_mdns", ROOT / "scripts/configure-uno-q-mdns.py")
compose_config = importlib.util.module_from_spec(compose_spec)
compose_spec.loader.exec_module(compose_config)


class SetupTests(unittest.TestCase):
    def test_compose_project_name_is_current_and_idempotent(self):
        legacy = "name: another-project\nservices:\n  main:\n    image: example\n"
        expected = "name: virtualglove\nservices:\n  main:\n    image: example\n"
        self.assertEqual(compose_config.configure_project_name(legacy), expected)
        self.assertEqual(compose_config.configure_project_name(expected), expected)
        self.assertEqual(
            compose_config.configure_project_name("services:\n  main:\n    image: example\n"),
            expected,
        )
        with self.assertRaisesRegex(ValueError, "at most one"):
            compose_config.configure_project_name(
                "name: old\nname: duplicate\nservices:\n  main:\n    image: example\n")

    def test_retired_buster_source_is_detected_without_touching_pi_archive(self):
        sources = [
            ("/etc/apt/sources.list",
             "deb http://raspbian.raspberrypi.org/raspbian buster main contrib\n"
             "deb http://archive.raspberrypi.org/debian buster main\n"),
            ("/etc/apt/sources.list.d/current.list",
             "deb http://deb.debian.org/debian bookworm main\n"),
        ]
        self.assertEqual(setup.retired_buster_sources(sources), ["/etc/apt/sources.list"])
        repaired = sources[0][1].replace(
            "http://raspbian.raspberrypi.org/raspbian",
            "https://legacy.raspbian.org/raspbian")
        self.assertEqual(setup.retired_buster_sources([("repaired", repaired)]), [])

    def test_retropie_source_preflight_fails_before_writes(self):
        """An obsolete package source must leave current configuration untouched."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/opt/")):
                    return root / str(path).lstrip("/")
                return path

            mapped("/opt/retropie/configs/all").mkdir(parents=True)
            with patch.object(setup, "Path", side_effect=mapped), \
                    patch.object(
                        setup, "check_retropie_package_sources",
                        side_effect=ValueError("obsolete package source"),
                    ), \
                    patch.object(setup, "write_file") as write:
                with self.assertRaisesRegex(ValueError, "obsolete package source"):
                    setup.install_retropie("virtualglove.local")
            write.assert_not_called()

    def test_retropie_hook_preflight_fails_before_configuration_writes(self):
        """An incompatible cabinet hook must not change current configuration."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/opt/")):
                    return root / str(path).lstrip("/")
                return path

            base = mapped("/opt/retropie/configs/all")
            base.mkdir(parents=True)
            (base / "runcommand-onstart.sh").write_text(
                "#!/usr/bin/python3\nprint('custom cabinet hook')\n"
            )
            with patch.object(setup, "Path", side_effect=mapped), \
                    patch.object(setup, "check_retropie_package_sources"):
                with self.assertRaisesRegex(ValueError, "not a supported shell script"):
                    setup.install_retropie("virtualglove.local")

    def test_unoq_startup_requires_matching_matrix_firmware(self):
        import io
        matched = io.BytesIO(b'{"firmware":{"state":"matched"}}')
        with patch.object(setup.urllib.request, "urlopen", return_value=matched):
            setup.wait_unoq()
        unavailable = [io.BytesIO(b'{"firmware":{"state":"unavailable"}}')
                       for _ in range(90)]
        with patch.object(setup.urllib.request, "urlopen", side_effect=unavailable), \
                patch.object(setup.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "startup validation failed"):
                setup.wait_unoq()

    def test_hook_inserted_before_exit_and_is_idempotent(self):
        original = "#!/bin/bash\necho existing\nexit 0\n"
        updated = setup.hook_content(original, "start")
        self.assertIn(original.split("\n", 1)[1], updated)
        self.assertLess(updated.index("virtualglove.sh"), updated.index("exit 0"))
        self.assertEqual(setup.hook_content(updated, "start"), updated)
        with self.assertRaises(ValueError):
            setup.hook_content("#!/usr/bin/python3\nprint('custom')\n", "start")

    def test_recalbox_hook_preserves_custom_startup_and_is_idempotent(self):
        original = "#!/bin/sh\necho cabinet-lighting \"$1\"\n"
        updated = setup.recalbox_custom_hook(original)
        self.assertIn("echo cabinet-lighting", updated)
        self.assertIn('sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service "$1"', updated)
        self.assertEqual(setup.recalbox_custom_hook(updated), updated)

    def test_player1_device_listing_uses_stable_ids(self):
        module = Mock()
        module.controller_candidates.return_value = [
            {"id": "abc123", "name": "Configured Pad"}
        ]
        with patch.object(setup, "merged_controller_module", return_value=module), \
                patch("builtins.print") as output:
            setup.list_player1_devices("recalbox")
        output.assert_called_once_with("abc123  Configured Pad")

    def test_retired_runtime_scan_matches_only_exact_managed_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            commands = {
                "101": [b"/usr/bin/python3", b"-m",
                        b"power" + b"glove_vision.receiver", b"--listen"],
                "102": [b"/usr/bin/python3", b"-m", b"virtualglove.receiver"],
                "103": [b"sh", b"-c", b"power" + b"glove_vision.receiver"],
                "104": [b"/usr/bin/python3", b"-m",
                        b"power" + b"glove_vision.unmanaged_tool"],
            }
            for pid, arguments in commands.items():
                path = proc / pid
                path.mkdir()
                (path / "cmdline").write_bytes(b"\0".join(arguments) + b"\0")
            self.assertEqual(setup.retired_runtime_processes(proc), [101])
            self.assertEqual(setup.managed_runtime_processes(proc), [101, 102])

    def test_saved_player1_controller_must_belong_to_current_platform(self):
        module = Mock()
        module.load_controller.return_value = {"platform": "recalbox"}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(setup, "merged_controller_module", return_value=module), \
                patch.object(
                    setup, "merged_controller_paths",
                    return_value=(Path(directory) / "es_input.cfg",
                                  Path(directory) / "player1-controller.json"),
                ):
            (Path(directory) / "player1-controller.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "belongs to recalbox"):
                setup.configure_merged_player1("batocera")

    def test_existing_player1_mapping_refreshes_from_connected_frontend(self):
        module = Mock()
        saved = {"format": 1, "platform": "batocera", "id": "pad",
                 "name": "Pad", "mapping": [{"name": "start", "type": "button",
                                                "code": 1, "value": 1}]}
        refreshed = {"id": "pad", "name": "Pad",
                     "mapping": [{"name": "start", "type": "button", "code": 1,
                                  "evdev_code": 158, "value": 1}]}
        module.load_controller.return_value = dict(saved)
        module.controller_candidates.return_value = [refreshed]
        module.find_saved_controller.return_value = refreshed
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(setup, "merged_controller_module", return_value=module), \
                patch.object(setup, "BACKUPS", Path(directory).resolve() / "backups"), \
                patch.object(setup, "merged_controller_paths",
                             return_value=(Path(directory).resolve() / "es_input.cfg",
                                           Path(directory).resolve() / "player1-controller.json")):
            config = Path(directory).resolve() / "player1-controller.json"
            config.write_text("{}")
            setup.configure_merged_player1("batocera")
            self.assertEqual(json.loads(config.read_text())["mapping"], refreshed["mapping"])

    def test_check_mode_never_runs_an_installer(self):
        with patch.object(setup.sys, "argv", ["setup-machine.py", "recalbox", "--check"]), \
                patch.object(setup.sys, "platform", "linux"), \
                patch.object(setup, "install_recalbox") as install, \
                patch.object(setup, "check_recalbox"), \
                patch.object(setup.Report, "finish", return_value=0):
            self.assertEqual(setup.main(), 0)
        install.assert_not_called()

    def test_files_are_backed_up_and_tokens_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            file = root / "settings"
            file.write_text("original")
            with patch.object(setup, "BACKUPS", root / "backups"):
                setup.write_file(file, "new", preserve=True)
                self.assertEqual(file.read_text(), "original")
                setup.write_file(file, "new")
                self.assertEqual(file.read_text(), "new")
                backups = list((root / "backups").rglob("settings"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(), "original")
                link = root / "link"
                link.symlink_to(file)
                with self.assertRaises(ValueError):
                    setup.write_file(link, "bad")

    def test_runtime_name_migration_refuses_pending_shutdown_request(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / "data").mkdir()
            (app / "data/shutdown-request").touch()

            class AppPath:
                def __str__(self):
                    return "/home/arduino/ArduinoApps/virtualglove"

                def __truediv__(self, relative):
                    return app / relative

            with patch.object(setup, "SOURCE", AppPath()):
                with self.assertRaisesRegex(ValueError, "pending shutdown request"):
                    setup.install_unoq_runtime_names()

    def test_runtime_name_install_writes_only_current_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app = root / "app"
            (app / "data").mkdir(parents=True)
            (app / "uno-q").mkdir()
            for original in (ROOT / "uno-q").glob("virtualglove-*"):
                (app / "uno-q" / original.name).write_bytes(original.read_bytes())

            class AppPath:
                def __str__(self):
                    return "/home/arduino/ArduinoApps/virtualglove"

                def __truediv__(self, relative):
                    return app / relative

            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/usr/local/")):
                    return root / str(path).lstrip("/")
                return path

            with patch.object(setup, "SOURCE", AppPath()), \
                    patch.object(setup, "Path", side_effect=mapped), \
                    patch.object(setup, "BACKUPS", root / "backups"), \
                    patch.object(setup, "run") as command, \
                    patch.object(setup, "install_early_start"), \
                    patch.object(setup, "install_wifi_status"), \
                    patch.object(setup.pwd, "getpwnam", return_value=SimpleNamespace(
                        pw_uid=os.getuid(), pw_gid=os.getgid(),
                        pw_dir=str(root / "home/arduino"),
                    )):
                setup.install_unoq_runtime_names()
            calls = [item.args for item in command.call_args_list]
            self.assertTrue((mapped("/etc/systemd/system") /
                             "virtualglove-system-shutdown.service").is_file())

    def test_runtime_name_upgrade_retires_exact_legacy_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app = root / "app"
            (app / "data").mkdir(parents=True)
            (app / "uno-q").mkdir()
            for original in (ROOT / "uno-q").glob("virtualglove-*"):
                (app / "uno-q" / original.name).write_bytes(original.read_bytes())
            home = root / "home/arduino"
            old_user_unit = home / ".config/systemd/user/powerglove-early-start.service"
            old_user_unit.parent.mkdir(parents=True)
            old_user_unit.write_text("legacy unit")
            old_user_helper = home / ".local/lib/powerglove/uno-q-early-start.py"
            old_user_helper.parent.mkdir(parents=True)
            old_user_helper.write_text("legacy helper")

            class AppPath:
                def __str__(self):
                    return "/home/arduino/ArduinoApps/virtualglove"

                def __truediv__(self, relative):
                    return app / relative

            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/usr/local/")):
                    return root / str(path).lstrip("/")
                return path

            legacy = [
                "/etc/systemd/system/powerglove-system-shutdown.path",
                "/etc/systemd/system/powerglove-camera-recovery.path",
                "/etc/systemd/system/powerglove-wifi-status.timer",
                "/etc/systemd/system/powerglove-system-shutdown.service",
                "/etc/systemd/system/powerglove-camera-recovery.service",
                "/etc/systemd/system/powerglove-wifi-status.service",
                "/etc/tmpfiles.d/powerglove-system-shutdown.conf",
                "/etc/tmpfiles.d/powerglove-camera-recovery.conf",
                "/usr/local/libexec/powerglove-camera-recovery",
                "/usr/local/libexec/powerglove-wifi-status",
            ]
            for name in legacy:
                path = mapped(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("legacy")
            account = SimpleNamespace(
                pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home)
            )
            with patch.object(setup, "SOURCE", AppPath()), \
                    patch.object(setup, "Path", side_effect=mapped), \
                    patch.object(setup, "BACKUPS", root / "backups"), \
                    patch.object(setup, "run") as command, \
                    patch.object(setup, "install_early_start"), \
                    patch.object(setup, "install_wifi_status"), \
                    patch.object(setup.pwd, "getpwnam", return_value=account):
                setup.install_unoq_runtime_names()
                expected_user_disable = tuple(setup.user_systemctl(
                    "disable", "--now", "powerglove-early-start.service"
                ))

            for name in legacy:
                self.assertFalse(mapped(name).exists(), name)
            self.assertFalse(old_user_unit.exists())
            self.assertFalse(old_user_helper.exists())
            command.assert_any_call(
                "systemctl", "disable", "--now",
                "powerglove-system-shutdown.path",
            )
            command.assert_any_call(*expected_user_disable)

    def test_early_start_installs_current_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / "home"
            (home / ".config/systemd/user").mkdir(parents=True)
            account = SimpleNamespace(
                pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home)
            )
            with patch.object(setup, "BACKUPS", root / "backups"), \
                    patch.object(setup.pwd, "getpwnam", return_value=account), \
                    patch.object(setup, "run") as command, \
                    patch.object(setup.os, "chown"):
                setup.install_early_start()
                expected_enable = tuple(setup.user_systemctl(
                    "enable", "virtualglove-early-start.service"
                ))
                expected_reset = tuple(setup.user_systemctl(
                    "reset-failed", "virtualglove-early-start.service"
                ))
            self.assertTrue((home / ".config/systemd/user" /
                             "virtualglove-early-start.service").is_file())
            command.assert_any_call(*expected_enable)
            command.assert_any_call(*expected_reset)

    def test_retropie_install_twice_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/opt/", "/dev/", "/usr/local/")):
                    return root / str(path).lstrip("/")
                return path
            base = mapped("/opt/retropie/configs/all")
            base.mkdir(parents=True)
            hook = base / "runcommand-onstart.sh"
            hook.write_text("#!/bin/sh\necho lighting\nexit 0\n")
            config = mapped("/etc/virtualglove")
            config.mkdir(parents=True)
            (config / "token").write_text("existing-private-token")
            (config / "launcher.json").write_text('{"uno_q":"existing.local"}')
            (config / "games.json").write_text('{"custom":"game"}')
            with patch.object(setup, "Path", side_effect=mapped), patch.object(setup, "BACKUPS", root / "backups"), patch.object(setup, "run") as command, patch.object(setup.os, "chown"), patch.object(setup.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=100)):
                setup.install_retropie("new.local")
                first = hook.read_text()
                setup.install_retropie("new.local")
            self.assertEqual(hook.read_text(), first)
            self.assertEqual((config / "token").read_text(), "existing-private-token")
            launcher = json.loads((config / "launcher.json").read_text())
            self.assertEqual(launcher["uno_q"], "existing.local")
            self.assertEqual(launcher["controller_router"]["platform"], "retropie")
            self.assertEqual((config / "games.json").read_text(), '{"custom":"game"}')
            self.assertTrue(mapped("/opt/virtualglove/bin/virtualglove-receiver").exists())
            self.assertTrue(mapped("/opt/virtualglove/bin/virtualglove-controller-router").exists())
            self.assertEqual(
                mapped("/usr/local/bin/virtualglove-controller-router").read_text(),
                '#!/bin/sh\nexec /opt/virtualglove/bin/virtualglove-controller-router "$@"\n',
            )
            self.assertTrue(mapped("/etc/systemd/system/virtualglove-receiver.timer").exists())
            self.assertIn("echo lighting", first)
            command.assert_any_call("apt-get", "install", "-y", "python3", "python3-evdev", "openssl", "avahi-daemon", "libnss-mdns")
            command.assert_any_call("systemctl", "enable", "--now", "avahi-daemon")

    def test_unoq_install_twice_preserves_private_data_and_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app = root / "app"
            (app / ".cache").mkdir(parents=True)
            (app / "data").mkdir()
            (app / "scripts").mkdir()
            (app / "uno-q").mkdir()
            (app / "data/device.json").write_text('{"token":"keep-this-private","profile":"off"}')
            compose = app / ".cache/app-compose.yaml"
            compose.write_text("services:\n  main:\n    volumes:\n    - /app:/app\n    ports:\n    - 8088:8088\n")
            for original in (ROOT / "uno-q").glob("virtualglove-*"):
                (app / "uno-q" / original.name).write_bytes(original.read_bytes())
            (app / "scripts/configure-uno-q-mdns.py").write_bytes((ROOT / "scripts/configure-uno-q-mdns.py").read_bytes())
            class AppPath:
                def __str__(self):
                    return "/home/arduino/ArduinoApps/virtualglove"
                def __truediv__(self, relative):
                    return app / relative
            def mapped(value):
                path = Path(value)
                return root / str(path).lstrip("/") if str(path).startswith(("/etc/", "/usr/local/")) else path
            with patch.object(setup, "SOURCE", AppPath()), patch.object(setup, "Path", side_effect=mapped), patch.object(setup, "BACKUPS", root / "backups"), patch.object(setup, "run") as command, patch.object(setup, "install_early_start") as early, patch.object(setup.os, "chown"), patch.object(setup.socket, "gethostname", return_value="VirtualGlove"), patch.object(setup.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir=str(root / "home/arduino"))):
                setup.install_unoq(None)
                first = compose.read_text()
                setup.install_unoq(None)
            command.assert_any_call(
                "apt-get", "install", "-y", "avahi-daemon", "libnss-mdns", "uhubctl"
            )
            command.assert_any_call("systemctl", "enable", "--now", "avahi-daemon")
            self.assertEqual(first, compose.read_text())
            self.assertEqual(first.count("target: /run/avahi-daemon"), 1)
            self.assertEqual(first.count("- 8443:8443"), 1)
            self.assertEqual(first.count("bricks/local/profile_control/brick_compose.yaml"), 1)
            self.assertTrue(first.startswith("name: virtualglove\n"))
            self.assertEqual((app / "data/device.json").read_text(), '{"token":"keep-this-private","profile":"off"}')
            self.assertEqual((app / "data/controller-hostname").read_text(), "virtualglove\n")
            self.assertTrue(mapped("/etc/systemd/system/virtualglove-system-shutdown.path").exists())
            service = mapped("/etc/systemd/system/virtualglove-system-shutdown.service").read_text()
            self.assertIn("ExecStart=/usr/bin/systemctl --no-block halt", service)
            self.assertNotIn("--no-block poweroff", service)
            self.assertTrue(mapped("/etc/systemd/system/virtualglove-camera-recovery.path").exists())
            camera_service = mapped("/etc/systemd/system/virtualglove-camera-recovery.service").read_text()
            self.assertIn("/usr/local/libexec/virtualglove-camera-recovery", camera_service)
            self.assertTrue(mapped("/usr/local/libexec/virtualglove-camera-recovery").exists())
            command.assert_any_call(
                "/usr/local/libexec/virtualglove-camera-recovery", "--configure-if-present"
            )
            command.assert_any_call("systemctl", "enable", "--now", "virtualglove-camera-recovery.path")
            command.assert_any_call(
                "env", "APP_HOME=/home/arduino/ArduinoApps/virtualglove",
                "docker", "compose", "-f", compose, "up", "-d", "--force-recreate"
            )
