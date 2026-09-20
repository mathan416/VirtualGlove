# Project: VirtualGlove
# File: tests/test_install_packages.py
# Purpose: Test release validation, safe updates, and installer entry points without host changes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Covered the canonical virtualglove directory and recoverable legacy migration.
#   2026-09-11 - Verified upgrades stop both possible App Lab Compose projects.
#   2026-09-11 - Covered first-install Controller naming, conflicts, and upgrade preservation.
#   2026-09-11 - Covered hostname and LAN-IP URLs in UNO Q completion output.
#   2026-09-11 - Covered cache-free loading from an extracted release tree.
#   2026-09-05 - Covered required renewable game-session package members.
#   2026-09-05 - Required App Lab builds to refresh their checksum companion.
#   2026-09-04 - Added two-machine installation regression coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise real staging and archive handling with simulated privileged commands."""
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install-package.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PackageContentTests(unittest.TestCase):
    def test_completed_console_upgrade_rotates_only_routine_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            script = source / "scripts/rotate-deployment-backups.py"
            script.parent.mkdir(parents=True)
            script.write_text("# test\n")
            setup = SimpleNamespace(BACKUPS=root / "backups/20260920-120000-1")
            with patch.object(installer.subprocess, "run",
                              return_value=SimpleNamespace(returncode=0)) as command:
                installer.rotate_console_backups(source, setup, "recalbox")
                installer.rotate_console_backups(source, setup, "uno-q")
            command.assert_called_once_with(
                [installer.sys.executable, str(script), str(root / "backups"),
                 "--keep", "5"], check=False)

    def test_retropie_upgrade_recognizes_current_launcher_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "etc/virtualglove/launcher.json"
            self.assertFalse(installer.retropie_launcher_exists(current))
            current.parent.mkdir(parents=True)
            current.write_text('{"uno_q":"existing.local"}')
            self.assertTrue(installer.retropie_launcher_exists(current))

    def test_controller_hostname_validation(self):
        for value, expected in (("VirtualGlove", "virtualglove"),
                                ("kids-room.local", "kids-room"),
                                ("vg2", "vg2")):
            self.assertEqual(installer.valid_controller_hostname(value), expected)
        for value in ("", "-virtualglove", "virtualglove-", "two names", "10",
                      "localhost", "local", "x" * 64):
            with self.subTest(value=value), self.assertRaises(Exception):
                installer.valid_controller_hostname(value)

    def test_fresh_interactive_install_suggests_and_confirms_virtualglove(self):
        with patch.object(installer.sys.stdin, 'isatty', return_value=True), \
                patch('builtins.input', side_effect=['', '']) as prompt:
            self.assertEqual(installer.select_controller_hostname(None, False), 'virtualglove')
        self.assertEqual(prompt.call_count, 2)

    def test_existing_install_is_never_renamed(self):
        with patch('builtins.input') as prompt:
            self.assertIsNone(installer.select_controller_hostname(None, True))
            with self.assertRaisesRegex(ValueError, 'only for a first installation'):
                installer.select_controller_hostname('another-name', True)
        prompt.assert_not_called()

    def test_noninteractive_fresh_install_preserves_existing_machine_name(self):
        with patch.object(installer.sys.stdin, 'isatty', return_value=False), \
                patch.object(installer.socket, 'gethostname', return_value='arduino'), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertIsNone(installer.select_controller_hostname(None, False))
        self.assertIn('preserving Controller name arduino', output.getvalue())

    def test_hostname_conflict_excludes_this_controllers_addresses(self):
        response = b'10.0.2.96 STREAM virtualglove.local\n10.0.2.96 DGRAM\n'
        with patch.object(installer.subprocess, 'check_output', return_value=response), \
                patch.object(installer, 'local_ipv4_addresses', return_value={'10.0.2.96'}):
            self.assertFalse(installer.hostname_conflicts('virtualglove'))
        with patch.object(installer.subprocess, 'check_output', return_value=response), \
                patch.object(installer, 'local_ipv4_addresses', return_value={'10.0.2.105'}):
            self.assertTrue(installer.hostname_conflicts('virtualglove'))

    def test_local_hosts_identity_is_changed_without_losing_aliases(self):
        original = '127.0.0.1 localhost\n127.0.1.1 Arduino old-alias # board\n'
        changed = installer.hosts_with_controller_name(original, 'Arduino', 'virtualglove')
        self.assertIn('127.0.1.1\tvirtualglove old-alias # board', changed)
        self.assertIn('127.0.0.1 localhost', changed)

    def test_configure_hostname_backs_up_managed_identity_and_sets_runtime_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hostname = root / 'hostname'
            hosts = root / 'hosts'
            hostname.write_text('Arduino\n')
            hosts.write_text('127.0.1.1 Arduino\n')
            setup = SimpleNamespace(write_file=Mock(), run=Mock())

            def write_file(path, content):
                target = hostname if str(path) == '/etc/hostname' else hosts
                target.write_text(content)

            setup.write_file.side_effect = write_file
            real_path = installer.Path
            with patch.object(installer.socket, 'gethostname', return_value='Arduino'), \
                    patch.object(installer, 'hostname_conflicts', return_value=False), \
                    patch.object(installer, 'Path', side_effect=lambda value: hosts if str(value) == '/etc/hosts' else real_path(value)):
                self.assertEqual(installer.configure_controller_hostname(setup, 'virtualglove'),
                                 'virtualglove')
            self.assertEqual(hostname.read_text(), 'virtualglove\n')
            self.assertIn('virtualglove', hosts.read_text())
            setup.run.assert_called_once_with('hostnamectl', 'set-hostname', 'virtualglove')

    def test_controller_urls_include_mdns_and_physical_ipv4_addresses(self):
        interfaces = [
            {"ifname": "lo", "addr_info": [
                {"family": "inet", "scope": "host", "local": "127.0.0.1"}]},
            {"ifname": "wlan0", "addr_info": [
                {"family": "inet", "scope": "global", "local": "10.0.2.96"}]},
            {"ifname": "end0", "addr_info": [
                {"family": "inet", "scope": "global", "local": "192.168.1.42"}]},
            {"ifname": "docker0", "addr_info": [
                {"family": "inet", "scope": "global", "local": "172.17.0.1"}]},
        ]
        with patch.object(installer.socket, 'gethostname', return_value='VirtualGlove'), \
                patch.object(installer.subprocess, 'check_output',
                             return_value=json.dumps(interfaces).encode()), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            installer.print_controller_urls()
        text = output.getvalue()
        self.assertIn('http://VirtualGlove.local:8088/dashboard', text)
        self.assertIn('https://10.0.2.96:8443/setup', text)
        self.assertIn('http://192.168.1.42:8088/help', text)
        self.assertNotIn('172.17.0.1', text)

    def test_controller_urls_tolerate_address_discovery_failure(self):
        with patch.object(installer.socket, 'gethostname', return_value='virtualglove.local'), \
                patch.object(installer.subprocess, 'check_output', side_effect=OSError('no ip')), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            installer.print_controller_urls()
        text = output.getvalue()
        self.assertIn('http://virtualglove.local:8088/dashboard', text)
        self.assertIn('IP address: not available yet', text)

    def test_precompiled_staging_replaces_sketch_sources_with_firmware(self):
        import runpy
        module = runpy.run_path(str(ROOT / 'scripts/application-payload.py'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'
            destination = Path(directory) / 'destination'
            (root / 'sketch').mkdir(parents=True)
            (root / 'sketch/sketch.ino').write_text('source')
            (root / 'app.yaml').write_text('name: test')
            firmware = root / 'output/matrix-firmware'
            firmware.mkdir(parents=True)
            for name in ('manifest.json', 'virtualglove-matrix.elf-zsk.bin',
                         'zephyr-arduino_uno_q_stm32u585xx.elf', 'flash_sketch.cfg'):
                (firmware / name).write_text(name)
            with patch.object(module['subprocess'], 'run'), \
                    patch.dict(module['stage'].__globals__, {
                        'selected_files': lambda *_args, **_kwargs:
                            ['app.yaml', 'sketch/sketch.ino']
                    }):
                module['stage'](root, destination, precompiled_matrix=True)
            self.assertTrue((destination / 'firmware/matrix/manifest.json').is_file())
            self.assertFalse((destination / 'sketch/sketch.ino').exists())

    def test_app_lab_builder_refreshes_companion_checksum(self):
        builder = (ROOT / 'scripts/build-app-lab-package.sh').read_text()
        self.assertIn('readonly OUTPUT_SHA="${OUTPUT_ZIP}.sha256"', builder)
        self.assertIn('hashlib.sha256(archive.read_bytes()).hexdigest()', builder)
        self.assertIn('mv "${OUTPUT_SHA_TMP}" "${OUTPUT_SHA}"', builder)

    def test_development_deploy_uses_a_compressed_archive(self):
        deploy = (ROOT / 'scripts/deploy-uno-q-wifi.sh').read_text()
        self.assertIn('virtualglove-deploy.tar.gz', deploy)
        self.assertIn('-czf "${LOCAL_ARCHIVE}"', deploy)
        self.assertIn('-xzf \'${REMOTE_ARCHIVE}\'', deploy)

    def test_local_matrix_exports_rejected_but_guide_images_allowed(self):
        spec = importlib.util.spec_from_file_location(
            'package_verifier', ROOT / 'scripts/verify-app-lab-package.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'package.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('VirtualGlove/assets/matrix/A.png', 'duplicate')
                output.writestr('VirtualGlove/docs/images/matrix/A.jpg', 'guide')
            errors = verifier.archive_errors(archive)
            duplicates = [error for error in errors if 'local duplicate matrix' in error]
            self.assertEqual(len(duplicates), 1)
            self.assertIn('assets/matrix/A.png', duplicates[0])

    def test_engineering_tools_are_rejected_from_ordinary_package(self):
        spec = importlib.util.spec_from_file_location(
            'package_verifier_engineering', ROOT / 'scripts/verify-app-lab-package.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'package.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr(
                    'VirtualGlove/scripts/benchmark-vision-replay.py', 'engineering')
            errors = verifier.archive_errors(archive)
            self.assertTrue(any('engineering-only file included' in error for error in errors))

    def test_app_lab_package_rejects_legacy_service_files(self):
        spec = importlib.util.spec_from_file_location(
            'package_verifier_legacy_services', ROOT / 'scripts/verify-app-lab-package.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'package.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr(
                    'VirtualGlove/uno-q/powerglove-wifi-status.service', 'legacy')
            errors = verifier.archive_errors(archive)
            self.assertIn(
                'legacy PowerGlove runtime file included: '
                'VirtualGlove/uno-q/powerglove-wifi-status.service', errors)


class ArchiveTests(unittest.TestCase):
    def package(self, directory, machine='retropie', extra=None):
        archive = Path(directory) / 'package.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('VirtualGlove/install-release.json', json.dumps(
                dict(format=1, machine=machine, version='dev-test')))
            for name in ('scripts/setup-machine.py', 'scripts/installation-manifest.py',
                         'scripts/install-nestopia-powerglove.sh',
                         'scripts/install-powerglove-dot.sh',
                         'scripts/configure-super-glove-ball-core.py',
                         'src/virtualglove/receiver.py',
                         'src/virtualglove/gesture.py',
                         'src/virtualglove/tracker.py',
                         'src/virtualglove/tuning.py',
                         'src/virtualglove/vision_app.py',
                         'src/virtualglove/profile_control.py',
                         'src/virtualglove/retropie_hook.py',
                         'src/virtualglove/controller_router.py',
                         'config/games.json', 'config/profiles.json',
                         'THIRD_PARTY_NOTICES.md',
                         'retropie/virtualglove-receiver.service',
                         'retropie/virtualglove-receiver.timer',
                         'retropie/virtualglove-games.service',
                         'retropie/virtualglove-controller-router.service',
                         'retropie/bin/virtualglove-retropie-hook',
                         'retropie/bin/virtualglove-receiver',
                         'retropie/bin/virtualglove-games',
                         'retropie/bin/virtualglove-pair',
                         'retropie/bin/virtualglove-profile',
                         'retropie/bin/virtualglove-bsb-zap',
                         'retropie/bin/virtualglove-dot',
                         'retropie/bin/virtualglove-controller-router',
                         'retropie/runcommand-onstart-virtualglove.sh',
                         'retropie/runcommand-onend-virtualglove.sh',
                         'native/nestopia-powerglove/nestopia-powerglove.patch',
                         'native/powerglove-dot/powerglove_dot.cpp',
                         'src/virtualglove/dot_launcher.py'):
                output.writestr('VirtualGlove/' + name, 'test')
            console_members = {
                'recalbox': (
                    'src/virtualglove/console_monitor.py',
                    'src/virtualglove/merged_gamepad.py',
                    'recalbox/virtualglove-service',
                    'recalbox/virtualglove-core-mount',
                    'scripts/build-recalbox-nestopia-powerglove.sh',
                    'scripts/build-recalbox-native-matrix.sh',
                    'scripts/install-recalbox-nestopia-powerglove.sh',
                    'scripts/configure-recalbox-super-glove-ball-core.py',
                    'scripts/verify-recalbox-native-core.py',
                    'native/recalbox/rpizero2/10.1/nestopia_powerglove_libretro.so',
                    'native/recalbox/rpizero2/10.1/nestopia-powerglove-source.tar.gz',
                    'python/ssh_pair.py',
                ),
                'batocera': (
                    'src/virtualglove/merged_gamepad.py',
                    'recalbox/virtualglove-service',
                    'batocera/VirtualGlove',
                    'batocera/virtualglove-game',
                    'batocera/virtualglove-core-mount',
                    'scripts/build-batocera-nestopia-powerglove.sh',
                    'scripts/build-batocera-native-matrix.sh',
                    'scripts/install-batocera-nestopia-powerglove.sh',
                    'scripts/configure-batocera-super-glove-ball-core.py',
                    'scripts/verify-batocera-native-core.py',
                    'native/batocera/bcm2835/43.1/nestopia_powerglove_libretro.so',
                    'native/batocera/bcm2835/43.1/nestopia-powerglove-source.tar.gz',
                    'python/ssh_pair.py',
                ),
            }
            for name in console_members.get(machine, ()):
                output.writestr('VirtualGlove/' + name, 'test')
            if machine == 'recalbox':
                output.writestr('VirtualGlove/native/recalbox/manifest.json', json.dumps({
                    'format': 2,
                    'cores': {'rpizero2': {'10.1': {
                        'file': 'rpizero2/10.1/nestopia_powerglove_libretro.so',
                        'source_file': 'rpizero2/10.1/nestopia-powerglove-source.tar.gz',
                    }}},
                }))
            if machine == 'batocera':
                output.writestr('VirtualGlove/native/batocera/manifest.json', json.dumps({
                    'format': 2,
                    'cores': {'bcm2835': {'43.1': {
                        'file': 'bcm2835/43.1/nestopia_powerglove_libretro.so',
                        'source_file': 'bcm2835/43.1/nestopia-powerglove-source.tar.gz',
                        'sha256': '0' * 64,
                        'source_sha256': '1' * 64,
                        'patch_sha256': '2' * 64,
                        'size': 4,
                        'source_size': 4,
                        'elf_class': 32,
                        'elf_machine': 'arm',
                        'batocera_version': '43.1',
                        'batocera_revision': '3' * 40,
                        'nestopia_revision': '4' * 40,
                        'build_image': 'example@sha256:' + '5' * 64,
                    }}},
                }))
            if extra:
                output.writestr(*extra)
        return archive

    def test_legacy_runtime_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.package(directory, extra=(
                'VirtualGlove/retropie/powerglove-receiver.service', 'legacy'))
            with self.assertRaisesRegex(ValueError, 'legacy PowerGlove runtime file'):
                installer.unpack(archive, Path(directory) / 'extract', 'retropie', 'dev-test')

    def test_valid_package_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.package(directory)
            source = installer.unpack(archive, Path(directory) / 'extract', 'retropie', 'dev-test')
            self.assertTrue((source / 'scripts/setup-machine.py').is_file())
            for machine, version in [('uno-q', 'dev-test'), ('retropie', 'v-other')]:
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    installer.unpack(archive, Path(directory) / 'bad', machine, version)

    def test_recalbox_and_batocera_packages_have_complete_identity(self):
        for machine in ('recalbox', 'batocera'):
            with self.subTest(machine=machine), tempfile.TemporaryDirectory() as directory:
                archive = self.package(directory, machine=machine)
                source = installer.unpack(
                    archive, Path(directory) / 'extract', machine, 'dev-test')
                self.assertTrue((source / 'src/virtualglove/merged_gamepad.py').is_file())
                self.assertTrue((source / machine).is_dir())

    def test_loading_and_staging_extracted_setup_creates_no_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'VirtualGlove'
            scripts = source / 'scripts'
            scripts.mkdir(parents=True)
            for name in ('setup-machine.py', 'installation-manifest.py'):
                (scripts / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
            (source / 'app.yaml').write_text('name: VirtualGlove\n')

            module = installer.load_setup(source)
            module.BACKUPS = root / 'backups'
            app = root / 'home/ArduinoApps/virtualglove'
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(installer, 'APP', app), \
                 patch.object(installer.pwd, 'getpwnam', return_value=account), \
                 patch.object(installer.os, 'chown'), patch.object(module, 'run'):
                installer.stage_unoq(source, module)

            self.assertFalse((scripts / '__pycache__').exists())
            self.assertFalse(list(source.rglob('*.pyc')))
            self.assertTrue((app / 'scripts/setup-machine.py').is_file())
            self.assertTrue((app / '.virtualglove-install.json').is_file())

    def test_traversal_private_files_and_links_rejected_before_extract(self):
        link = zipfile.ZipInfo('VirtualGlove/link')
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ('../escape', '/absolute', 'VirtualGlove/data/token',
                     'VirtualGlove/docs/cheatsheet.md', link):
            with tempfile.TemporaryDirectory() as directory:
                archive = self.package(directory, extra=(name, 'bad'))
                target = Path(directory) / 'extract'
                with self.assertRaises(ValueError):
                    installer.unpack(archive, target, 'retropie', 'dev-test')
                self.assertFalse(target.exists())

    def test_duplicate_and_incomplete_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.package(directory, extra=('VirtualGlove/config/games.json', 'duplicate'))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                installer.unpack(archive, Path(directory) / 'bad', 'retropie', 'dev-test')
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('VirtualGlove/install-release.json', json.dumps(
                    dict(format=1, machine='retropie', version='dev-test')))
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                installer.unpack(archive, Path(directory) / 'bad', 'retropie', 'dev-test')

    def test_fresh_and_repeat_unoq_staging_preserves_private_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source'
            source.mkdir()
            (source / 'app.yaml').write_text('new application')
            app = root / 'home/ArduinoApps/virtualglove'
            setup = installer.load_setup(ROOT)
            setup.BACKUPS = root / 'backups'
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(installer, 'APP', app), patch.object(installer.pwd, 'getpwnam', return_value=account), \
                 patch.object(installer.os, 'chown'), patch.object(setup, 'run') as command:
                installer.stage_unoq(source, setup)
                self.assertEqual((app / 'app.yaml').read_text(), 'new application')
                (app / 'data').mkdir()
                (app / 'data/device.json').write_text('private-pairing-and-tuning')
                (app / 'data/calibration.json').write_text('private-neutral-reference')
                (app / 'data/gesture-tuning.json').write_text('private-gesture-thresholds')
                (app / 'docs').mkdir()
                (app / 'docs/cheatsheet.md').write_text('local cabinet')
                (app / '.cache').mkdir()
                (app / '.cache/app-compose.yaml').write_text('generated')
                (app / 'sketch').mkdir()
                (source / 'app.yaml').write_text('upgrade')
                installer.stage_unoq(source, setup)
                self.assertFalse((app / 'sketch').exists())
                installer.stage_unoq(source, setup)
                self.assertEqual((app / 'data/device.json').read_text(), 'private-pairing-and-tuning')
                self.assertEqual((app / 'data/calibration.json').read_text(), 'private-neutral-reference')
                self.assertEqual((app / 'data/gesture-tuning.json').read_text(), 'private-gesture-thresholds')
                self.assertEqual((app / 'docs/cheatsheet.md').read_text(), 'local cabinet')
                command.assert_any_call('runuser', '-u', 'arduino', '--', 'arduino-app-cli', 'app', 'start', app)
                calls = [item.args for item in command.call_args_list]
                upgrade_start = [index for index, item in enumerate(calls)
                                 if item == ('runuser', '-u', 'arduino', '--',
                                             'arduino-app-cli', 'app', 'start', app)][1]
                expected = (
                    'env', 'APP_HOME=' + str(app), 'docker', 'compose', '-p',
                    'virtualglove', '-f', app / '.cache/app-compose.yaml',
                    'down', '--remove-orphans')
                command.assert_any_call(*expected)
                self.assertLess(calls.index(expected), upgrade_start)
                self.assertTrue(list((root / 'backups').rglob('app.yaml')))

    def test_unmanaged_old_sketch_files_are_not_silently_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source'
            source.mkdir()
            (source / 'app.yaml').write_text('release')
            app = root / 'app'
            (app / 'sketch').mkdir(parents=True)
            (app / 'sketch/local-note.txt').write_text('keep')
            setup = installer.load_setup(ROOT)
            setup.BACKUPS = root / 'backups'
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(installer, 'APP', app), \
                    patch.object(installer.pwd, 'getpwnam', return_value=account), \
                    patch.object(installer.os, 'chown'), patch.object(setup, 'run'):
                with self.assertRaisesRegex(ValueError, 'Unmanaged files remain'):
                    installer.stage_unoq(source, setup)
            self.assertEqual((app / 'sketch/local-note.txt').read_text(), 'keep')


class NamespaceUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = runpy.run_path(str(ROOT / 'scripts/installation-manifest.py'))
        self.old_package = 'power' + 'glove_vision'

    def released_042_install(self, root):
        old = root / 'src' / self.old_package
        old.mkdir(parents=True)
        files = {
            'src/' + self.old_package + '/__init__.py': b'old package\n',
            'src/' + self.old_package + '/receiver.py': b'old receiver\n',
            'scripts/setup-machine.py': b'old installer\n',
        }
        records = {}
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            records[name] = self.manifest['fingerprint'](path)
        (old / '__pycache__').mkdir()
        (old / '__pycache__/receiver.cpython-311.pyc').write_bytes(b'generated cache')
        (root / 'data').mkdir()
        (root / 'data/device.json').write_text('private pairing and calibration')
        (root / '.virtualglove-install.json').write_text(json.dumps({
            'format': 1, 'root': str(root), 'release': 'v0.4.2', 'files': records,
        }, indent=2))
        return files

    def current_source(self, directory):
        source = Path(directory) / 'release'
        (source / 'src/virtualglove').mkdir(parents=True)
        (source / 'src/virtualglove/__init__.py').write_text('current package\n')
        (source / 'scripts').mkdir()
        (source / 'scripts/setup-machine.py').write_text('current installer\n')
        (source / 'install-release.json').write_text(json.dumps({
            'format': 1, 'machine': 'retropie', 'version': 'v0.5.0',
        }))
        return source

    def test_042_upgrade_retires_namespace_and_preserves_private_data(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            root = directory / 'installed'
            old_files = self.released_042_install(root)
            source = self.current_source(directory)
            backup = directory / 'backup'
            result = self.manifest['apply'](source, root, backup)
            self.assertFalse((root / 'src' / self.old_package).exists())
            self.assertEqual(self.manifest['check'](root), [])
            self.assertTrue((root / 'src/virtualglove/__init__.py').is_file())
            self.assertEqual((root / 'data/device.json').read_text(),
                             'private pairing and calibration')
            retired_files = {name for name in old_files if self.old_package in name}
            self.assertTrue(retired_files.issubset(set(result['removed'])))
            for name in retired_files:
                self.assertTrue((backup / name).is_file())
            installed = json.loads((root / '.virtualglove-install.json').read_text())
            self.assertEqual(installed['release'], 'v0.5.0')
            self.assertFalse(any(self.old_package in name for name in installed['files']))

    def test_042_upgrade_backs_up_and_removes_modified_managed_retired_code(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            root = directory / 'installed'
            self.released_042_install(root)
            modified = root / 'src' / self.old_package / 'receiver.py'
            modified.write_text('local modification\n')
            source = self.current_source(directory)
            backup = directory / 'backup'
            result = self.manifest['apply'](source, root, backup)
            retired = 'src/' + self.old_package + '/receiver.py'
            self.assertIn(retired, result['backed_up_changes'])
            self.assertEqual((backup / retired).read_text(), 'local modification\n')
            self.assertFalse((root / 'src' / self.old_package).exists())
            self.assertTrue((root / 'src/virtualglove').is_dir())

    def test_untracked_retired_tree_requires_manual_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            root = directory / 'installed'
            old = root / 'src' / self.old_package
            old.mkdir(parents=True)
            (old / '__init__.py').write_text('untracked old package\n')
            source = self.current_source(directory)
            with self.assertRaisesRegex(ValueError, 'without an installation manifest'):
                self.manifest['apply'](source, root, directory / 'backup')
            self.assertTrue((old / '__init__.py').is_file())


class BootstrapTests(unittest.TestCase):
    def execute(self, args, call_result=0, **patches):
        script = (ROOT / 'scripts/install-retropie.sh').read_text()
        code = script.split("exec python3 -c '\n", 1)[1].rsplit("' \"$@\"", 1)[0]
        with patch('sys.argv', ['installer'] + args), patch('sys.platform', 'linux'), \
             patch('os.geteuid', return_value=1000), \
             patch('urllib.request.urlopen', **patches) as network, \
             patch('subprocess.call', return_value=call_result) as call:
            with self.assertRaises(SystemExit) as result:
                exec(compile(code, 'bootstrap', 'exec'), {'__name__': '__main__'})
            return result.exception.code, network, call

    def test_check_never_downloads(self):
        with patch.object(Path, 'is_file', return_value=True):
            result, network, call = self.execute(['--check'])
        self.assertEqual(result, 0)
        network.assert_not_called()
        self.assertIn('--check', call.call_args[0][0])

    def test_download_failure_never_invokes_sudo(self):
        result, _, call = self.execute(['--version', 'v-test'], side_effect=OSError('network interrupted'))
        self.assertEqual(result, 1)
        call.assert_not_called()

    def test_bad_checksum_never_invokes_sudo(self):
        result, _, call = self.execute(['--version', 'v-test'], side_effect=[
            io.BytesIO(('0' * 64 + '  install-package.py\n').encode()), io.BytesIO(b'corrupt')])
        self.assertEqual(result, 1)
        call.assert_not_called()

    def test_verified_development_package_and_denied_sudo(self):
        import hashlib
        driver, package = b'driver', b'package'
        sums = (hashlib.sha256(driver).hexdigest() + '  install-package.py\n' +
                hashlib.sha256(package).hexdigest() + '  VirtualGlove-RetroPie.zip\n').encode()
        result, network, call = self.execute(['--development', 'dev-test', '--peer', 'uno.local'],
                                             side_effect=[io.BytesIO(sums), io.BytesIO(driver), io.BytesIO(package)])
        self.assertEqual(result, 0)
        self.assertIn('dev-test', network.call_args[0][0])
        self.assertEqual(call.call_args[0][0][-2:], ['--peer', 'uno.local'])

    def test_uno_bootstrap_forwards_first_install_hostname(self):
        import hashlib
        script = (ROOT / 'scripts/install-uno-q.sh').read_text()
        code = script.split("exec python3 -c '\n", 1)[1].rsplit("' \"$@\"", 1)[0]
        driver, package = b'driver', b'package'
        sums = (hashlib.sha256(driver).hexdigest() + '  install-package.py\n' +
                hashlib.sha256(package).hexdigest() + '  VirtualGlove-Uno-Q.zip\n').encode()
        with patch('sys.argv', ['installer', '--development', 'dev-test',
                                '--hostname', 'family-room']), \
                patch('sys.platform', 'linux'), patch('os.geteuid', return_value=1000), \
                patch('urllib.request.urlopen', side_effect=[io.BytesIO(sums), io.BytesIO(driver),
                                                             io.BytesIO(package)]), \
                patch('subprocess.call', return_value=0) as call:
            with self.assertRaises(SystemExit):
                exec(compile(code, 'bootstrap', 'exec'), {'__name__': '__main__'})
        self.assertEqual(call.call_args[0][0][-2:], ['--hostname', 'family-room'])

    def test_latest_release_is_resolved_once_and_pinned_for_downloads(self):
        import hashlib
        driver, package = b'driver', b'package'
        sums = (hashlib.sha256(driver).hexdigest() + '  install-package.py\n' +
                hashlib.sha256(package).hexdigest() + '  VirtualGlove-RetroPie.zip\n').encode()
        result, network, call = self.execute([], side_effect=[
            io.BytesIO(b'{"tag_name":"v0.3.0"}'), io.BytesIO(sums),
            io.BytesIO(driver), io.BytesIO(package)])
        self.assertEqual(result, 0)
        self.assertTrue(network.call_args_list[0][0][0].endswith('/releases/latest'))
        for request in network.call_args_list[1:]:
            self.assertIn('/releases/download/v0.3.0/', request[0][0])
        self.assertEqual(call.call_args[0][0][-2:], ['--version', 'v0.3.0'])

    def test_denied_sudo_is_returned_to_user(self):
        with patch.object(Path, 'is_file', return_value=True):
            result, network, call = self.execute(['--check'], call_result=1)
        self.assertEqual(result, 1)
        network.assert_not_called()
        self.assertEqual(call.call_args[0][0][0], 'sudo')

    def test_no_tty_does_not_confirm(self):
        with patch.object(installer.sys.stdin, 'isatty', return_value=False):
            self.assertFalse(installer.confirm('interrupt?'))


if __name__ == '__main__':
    unittest.main()

class PreflightTests(unittest.TestCase):
    def test_wrong_platform_stops_before_commands(self):
        with patch.object(installer.sys, 'platform', 'darwin'), patch.object(installer.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'requires Linux'):
                installer.preflight('uno-q')
            command.assert_not_called()

    def test_active_retropie_requires_closed_game(self):
        with patch.object(installer.sys, 'platform', 'linux'), patch.object(installer.os, 'geteuid', return_value=0), \
             patch.object(installer.shutil, 'which', return_value='/usr/bin/command'), \
             patch.object(installer.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024 ** 3)), \
             patch.object(Path, 'is_dir', return_value=True), \
             patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
             patch.object(installer, 'confirm', return_value=False):
            with self.assertRaisesRegex(ValueError, 'close RetroArch'):
                installer.preflight('retropie')

    def test_active_unoq_denied_and_unknown_cli(self):
        for version, message in [(b'Arduino App CLI version 0.12.0\ndaemon version: 0.12.0', 'validated'),
                                 (b'Arduino App CLI version 0.13.0\ndaemon version: 0.13.0', 'active session')]:
            with patch.object(installer.sys, 'platform', 'linux'), patch.object(installer.os, 'geteuid', return_value=0), \
                 patch.object(installer.shutil, 'which', return_value='/usr/bin/command'), \
                 patch.object(installer.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024 ** 3)), \
                 patch.object(Path, 'read_bytes', return_value=b'arduino,imola'), \
                 patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'exists', return_value=False), \
                 patch.object(installer.pwd, 'getpwnam'), \
                 patch.object(installer.subprocess, 'check_output', return_value=version), \
                 patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"controller_enabled":true}')), \
                 patch.object(installer, 'confirm', return_value=False):
                with self.assertRaisesRegex(ValueError, message):
                    installer.preflight('uno-q')


class RuntimeLifecycleTests(unittest.TestCase):
    def test_retropie_publishers_stop_before_managed_files_are_replaced(self):
        setup = SimpleNamespace(managed_runtime_processes=Mock(return_value=[]))
        with patch('pathlib.Path.exists', return_value=True), \
                patch.object(installer.subprocess, 'run') as run:
            self.assertEqual(installer.stop_managed_runtime('retropie', setup),
                             'retropie')
        commands = [tuple(item.args[0]) for item in run.call_args_list]
        self.assertIn(('systemctl', 'stop', 'virtualglove-receiver.timer'), commands)
        self.assertIn(('systemctl', 'stop', 'virtualglove-receiver.service'), commands)
        self.assertIn(('systemctl', 'stop', 'virtualglove-games.service'), commands)
        self.assertIn(('systemctl', 'stop', 'virtualglove-controller-router.service'), commands)

    def test_retropie_receiver_cannot_remove_router_runtime_directory(self):
        receiver = (ROOT / 'retropie/virtualglove-receiver.service').read_text()
        router = (ROOT / 'retropie/virtualglove-controller-router.service').read_text()
        self.assertNotIn('RuntimeDirectory=virtualglove', receiver)
        self.assertIn('After=network-online.target virtualglove-controller-router.service', receiver)
        self.assertIn('RuntimeDirectory=virtualglove', router)

    def test_retropie_recovery_starts_router_before_receiver(self):
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'read_text', return_value='x' * 32), \
                patch.object(installer.subprocess, 'run') as run:
            installer.restart_managed_runtime('retropie')
        commands = [tuple(item.args[0]) for item in run.call_args_list]
        self.assertLess(
            commands.index(('systemctl', 'start', 'virtualglove-controller-router.service')),
            commands.index(('systemctl', 'start', 'virtualglove-receiver.service')),
        )

    def test_batocera_service_stops_before_managed_files_are_replaced(self):
        setup = SimpleNamespace(managed_runtime_processes=Mock(return_value=[]))
        with patch('pathlib.Path.is_file', return_value=True), \
                patch.object(installer.subprocess, 'run') as run:
            self.assertEqual(installer.stop_managed_runtime('batocera', setup),
                             'batocera')
        run.assert_called_once_with(
            ['batocera-services', 'stop', 'VirtualGlove'], check=False)

    def test_upgrade_refuses_to_replace_files_while_publishers_remain(self):
        setup = SimpleNamespace(managed_runtime_processes=Mock(return_value=[321]))
        with patch('pathlib.Path.is_file', return_value=False), \
                patch.object(installer.time, 'monotonic', side_effect=[0, 6]), \
                patch.object(installer.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'Could not stop existing'):
                installer.stop_managed_runtime('batocera', setup)


class GameSetupTests(unittest.TestCase):
    def test_optional_dot_test_builds_and_adds_rom_free_ports_entry(self):
        setup = installer.load_setup(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            def mapped(value):
                path = Path(value)
                if str(path).startswith(("/opt/retropie", "/home/pi")):
                    return root / str(path).lstrip("/")
                return path

            prefix = mapped("/opt/retropie")
            for path in (prefix / "libretrocores/lr-fceumm/fceumm_libretro.so",
                         prefix / "emulators/retroarch/bin/retroarch"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"binary")

            def command(*args):
                if args[0] == "bash" and "install-powerglove-dot.sh" in str(args[1]):
                    target = prefix / "libretrocores/lr-powerglove-dot/powerglove_dot_libretro.so"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"dot")

            account = SimpleNamespace(pw_dir="/home/pi", pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(setup, "Path", side_effect=mapped), \
                 patch.object(setup, "BACKUPS", root / "backups"), \
                 patch.object(setup, "registered_roms", return_value=[]), \
                 patch.object(setup, "run", side_effect=command) as run, \
                 patch.object(setup.pwd, "getpwnam", return_value=account), \
                 patch.object(setup.os, "chown"), \
                 patch.dict(os.environ, {"SUDO_USER": "pi"}):
                setup.configure_games(lambda message: "Calibration Test" in message)

            run.assert_any_call("apt-get", "install", "-y", "build-essential")
            launcher = mapped("/home/pi/RetroPie/roms/ports/VirtualGlove Calibration Test.sh")
            self.assertEqual(launcher.read_text(),
                             "#!/bin/sh\nexec /opt/virtualglove/bin/virtualglove-dot\n")
            self.assertEqual((prefix / "configs/nes/powerglove-native.cfg").read_text(),
                             'input_libretro_device_p1 = "517"\nvideo_threaded = "false"\n')

    def test_missing_emulator_offer_accept_and_decline(self):
        for accept in (True, False):
            setup = installer.load_setup(ROOT)
            with patch.object(Path, 'is_file', side_effect=lambda path=None: True) as exists, \
                 patch.object(setup.pwd, 'getpwnam', return_value=SimpleNamespace(pw_dir='/home/pi')), \
                 patch.dict(os.environ, {'SUDO_USER': 'pi'}), \
                 patch.object(setup, 'registered_roms', return_value=[]), patch.object(setup, 'run') as command:
                # Core, binary missing; Setup present; each package still missing until installed.
                exists.side_effect = [False, True] + ([False, False] if accept else []) + [False]
                setup.configure_games(lambda message: accept and "missing RetroArch/FCEUmm" in message)
            if accept:
                self.assertEqual(command.call_count, 4)
                self.assertIn('install_bin', command.call_args_list[0][0])
            else:
                command.assert_not_called()

    def test_native_core_offer_builds_and_registers_without_selecting_rom(self):
        setup = installer.load_setup(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            def mapped(value):
                path = Path(value)
                if str(path).startswith("/opt/retropie"):
                    return root / str(path).lstrip("/")
                return path

            prefix = mapped("/opt/retropie")
            fceumm = prefix / "libretrocores/lr-fceumm/fceumm_libretro.so"
            native = prefix / "libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so"
            retroarch = prefix / "emulators/retroarch/bin/retroarch"
            system = prefix / "configs/nes/emulators.cfg"
            for path in (fceumm, retroarch):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"binary")
            system.parent.mkdir(parents=True, exist_ok=True)
            system.write_text('default = "lr-fceumm"\nlr-fceumm = "/retroarch -L ' + str(fceumm) + ' %ROM%"\n')
            rom = root / "home/pi/RetroPie/roms/nes/Super Glove Ball (USA).nes"
            rom.parent.mkdir(parents=True)
            rom.write_bytes(b"test-only")

            def command(*args):
                if args[0] == "bash" and "install-nestopia-powerglove.sh" in str(args[1]):
                    native.parent.mkdir(parents=True, exist_ok=True)
                    native.write_bytes(b"native")

            real_temporary_directory = tempfile.TemporaryDirectory
            with patch.object(setup, "Path", side_effect=mapped), \
                 patch.object(setup, "BACKUPS", root / "backups"), \
                 patch.object(setup, "registered_roms", return_value=[(rom, "super_glove_ball")]), \
                 patch.object(setup.tempfile, "TemporaryDirectory",
                              side_effect=lambda **kwargs: real_temporary_directory(
                                  prefix=kwargs.get("prefix"), dir=str(root))), \
                 patch.object(setup, "run", side_effect=command) as run:
                setup.configure_games(lambda message: "lr-nestopia-powerglove" in message)

            run.assert_any_call("apt-get", "install", "-y", "git", "build-essential")
            self.assertIn("lr-nestopia-powerglove", system.read_text())
            games = prefix / "configs/all/emulators.cfg"
            self.assertFalse(games.exists())
            self.assertEqual(
                (prefix / "configs/nes/powerglove-native.cfg").read_text(),
                'input_libretro_device_p1 = "517"\nvideo_threaded = "false"\n',
            )

    def test_helper_failure_is_not_silently_accepted(self):
        setup = installer.load_setup(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            setup.SOURCE = ROOT
            account = SimpleNamespace(pw_dir=str(Path(directory).resolve()), pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(setup.pwd, 'getpwnam', return_value=account), patch.object(setup.os, 'chown'), \
                 patch.object(setup, 'run', side_effect=OSError('systemd unavailable')):
                with self.assertRaisesRegex(OSError, 'systemd unavailable'):
                    setup.install_early_start()
