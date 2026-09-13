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
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_machine", ROOT / "scripts/setup-machine.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
compose_spec = importlib.util.spec_from_file_location(
    "configure_uno_q_mdns", ROOT / "scripts/configure-uno-q-mdns.py")
compose_config = importlib.util.module_from_spec(compose_spec)
compose_spec.loader.exec_module(compose_config)


class SetupTests(unittest.TestCase):
    def test_compose_project_name_replaces_legacy_name_idempotently(self):
        legacy = "name: powerglove-vision\nservices:\n  main:\n    image: example\n"
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

    def test_retropie_source_preflight_fails_before_migration_or_writes(self):
        """An obsolete package source must leave legacy configuration untouched."""
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
                    patch.object(setup, "migrate_directory") as migrate, \
                    patch.object(setup, "write_file") as write:
                with self.assertRaisesRegex(ValueError, "obsolete package source"):
                    setup.install_retropie("virtualglove.local")
            migrate.assert_not_called()
            write.assert_not_called()

    def test_retropie_hook_preflight_fails_before_configuration_migration(self):
        """An incompatible cabinet hook must not start the legacy migration."""
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
                    patch.object(setup, "check_retropie_package_sources"), \
                    patch.object(setup, "migrate_directory") as migrate:
                with self.assertRaisesRegex(ValueError, "not a supported shell script"):
                    setup.install_retropie("virtualglove.local")
            migrate.assert_not_called()

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

    def test_private_legacy_settings_migrate_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            legacy = root / "legacy"
            current = root / "current"
            legacy.mkdir()
            (legacy / "token").write_text("paired-secret")
            self.assertTrue(setup.migrate_directory(legacy, current))
            self.assertEqual((current / "token").read_text(), "paired-secret")
            (current / "token").write_text("different")
            with self.assertRaisesRegex(ValueError, "differ"):
                setup.migrate_directory(legacy, current)
            legacy_file = root / "powerglove-camera.json"
            current_file = root / "virtualglove-camera.json"
            legacy_file.write_text('{"camera":"kept"}')
            self.assertTrue(setup.migrate_file(legacy_file, current_file))
            self.assertEqual(current_file.read_text(), '{"camera":"kept"}')

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

    def test_runtime_name_migration_stops_triggers_before_legacy_services(self):
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

            unit_root = mapped("/etc/systemd/system")
            unit_root.mkdir(parents=True)
            for name in (
                "powerglove-system-shutdown.path",
                "powerglove-system-shutdown.service",
                "powerglove-camera-recovery.path",
                "powerglove-camera-recovery.service",
            ):
                (unit_root / name).write_text(name)
            with patch.object(setup, "SOURCE", AppPath()), \
                    patch.object(setup, "Path", side_effect=mapped), \
                    patch.object(setup, "BACKUPS", root / "backups"), \
                    patch.object(setup, "run") as command, \
                    patch.object(setup, "install_early_start"), \
                    patch.object(setup, "install_wifi_status"):
                setup.install_unoq_runtime_names()
            calls = [item.args for item in command.call_args_list]
            stop_paths = (
                "systemctl", "stop",
                "powerglove-system-shutdown.path",
                "powerglove-camera-recovery.path",
            )
            stop_services = (
                "systemctl", "stop",
                "powerglove-system-shutdown.service",
                "powerglove-camera-recovery.service",
            )
            disable = (
                "systemctl", "disable",
                "powerglove-system-shutdown.path",
                "powerglove-system-shutdown.service",
                "powerglove-camera-recovery.path",
                "powerglove-camera-recovery.service",
            )
            self.assertLess(calls.index(stop_paths), calls.index(stop_services))
            self.assertLess(calls.index(stop_services), calls.index(disable))

    def test_early_start_retires_legacy_trial_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / "home"
            trial = home / ".config/systemd/user/powerglove-early-start-trial.service"
            trial.parent.mkdir(parents=True)
            trial.write_text("legacy trial")
            account = SimpleNamespace(
                pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(home)
            )
            with patch.object(setup, "BACKUPS", root / "backups"), \
                    patch.object(setup.pwd, "getpwnam", return_value=account), \
                    patch.object(setup, "run") as command, \
                    patch.object(setup.os, "chown"):
                setup.install_early_start()
                expected_disable = tuple(setup.user_systemctl(
                    "disable", "--now", "powerglove-early-start-trial.service"
                ))
            self.assertFalse(trial.exists())
            retired = list((root / "backups/retired").rglob(
                "powerglove-early-start-trial.service"
            ))
            self.assertEqual(len(retired), 1)
            command.assert_any_call(*expected_disable)

    def test_retropie_install_twice_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/etc/", "/opt/", "/dev/")):
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
            self.assertEqual((config / "launcher.json").read_text(), '{"uno_q":"existing.local"}')
            self.assertEqual((config / "games.json").read_text(), '{"custom":"game"}')
            self.assertTrue(mapped("/opt/virtualglove/bin/virtualglove-receiver").exists())
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
            with patch.object(setup, "SOURCE", AppPath()), patch.object(setup, "Path", side_effect=mapped), patch.object(setup, "BACKUPS", root / "backups"), patch.object(setup, "run") as command, patch.object(setup, "install_early_start") as early, patch.object(setup.os, "chown"), patch.object(setup.socket, "gethostname", return_value="VirtualGlove"), patch.object(setup.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1000, pw_gid=1000)):
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
            self.assertNotIn("name: powerglove-vision", first)
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
