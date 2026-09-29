# Project: VirtualGlove
# File: tests/test_console_recovery.py
# Purpose: Verify transactional console upgrade recovery in isolation.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-29 - Added release audit source documentation.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise console upgrade recovery without modifying a host or its services."""
import importlib.util
from pathlib import Path
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_installer', ROOT / 'scripts/install-package.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ConsoleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = self.root / 'installed'
        self.payload.mkdir()
        self.code = self.payload / 'receiver.py'
        self.code.write_text('previous receiver')
        self.code.chmod(0o751)
        self.config = self.root / 'launcher.json'
        self.config.write_text('{"paired": true}')
        self.token = self.root / 'token'
        self.token.write_text('private-pairing-value')
        self.token.chmod(0o600)
        self.new_file = self.root / 'new-hook'
        self.setup = SimpleNamespace(BACKUPS=self.root / 'backups/upgrade-1',
                                     managed_runtime_processes=lambda: [])
        self.setup.BACKUPS.mkdir(parents=True)
        self.paths = [self.payload, self.config, self.token, self.new_file]
        self.recovery = installer.ConsoleRecovery('retropie', self.setup, self.paths)
        self.states = {unit: {'active': 'inactive', 'enabled': 'disabled'}
                       for unit in installer.CONSOLE_UNITS}
        self.states['virtualglove-controller-router.service'] = {
            'active': 'active', 'enabled': 'enabled'}
        self.states['virtualglove-receiver.service'] = {
            'active': 'active', 'enabled': 'disabled'}
        self.real_restore_services = installer.restore_console_services
        for target, result in [('console_service_state', self.states),
                               ('stop_managed_runtime', None),
                               ('restore_console_services', None), ('detach_router_generator', None)]:
            mock = self.enterContext(patch.object(installer, target, return_value=result))
            setattr(self, target, mock)

    def change_install(self):
        self.code.write_text('new receiver')
        self.code.chmod(0o644)
        (self.payload / 'new-module.py').write_text('new code')
        self.config.write_text('{"paired": false}')
        self.new_file.write_text('new hook')

    def assert_restored(self):
        self.assertEqual(self.code.read_text(), 'previous receiver')
        self.assertEqual(self.code.stat().st_mode & 0o777, 0o751)
        self.assertEqual(self.config.read_text(), '{"paired": true}')
        self.assertEqual(self.token.read_text(), 'private-pairing-value')
        self.assertEqual(self.token.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.new_file.exists())
        self.assertFalse((self.payload / 'new-module.py').exists())
        self.restore_console_services.assert_called_with('retropie', self.states)

    def test_failure_after_payload_commit_restores_entire_install(self):
        before_owner = (self.code.stat().st_uid, self.code.stat().st_gid)
        self.recovery.begin()
        self.change_install()
        self.recovery.restore()
        self.assert_restored()
        self.assertEqual((self.code.stat().st_uid, self.code.stat().st_gid), before_owner)
        self.assertFalse(self.recovery.pending.exists())

    def test_interrupt_during_backup_recovers_activation_without_replacing_files(self):
        self.recovery.backup.mkdir()
        self.recovery.write_journal({'schema': 1, 'machine': 'retropie',
                                     'backup': str(self.recovery.backup), 'phase': 'preparing',
                                     'paths': [], 'services': self.states})
        self.recovery.restore()
        self.assert_restored()
        self.assertFalse(self.recovery.pending.exists())

    def test_success_keeps_new_files_and_removes_pending_journal(self):
        self.recovery.begin()
        self.change_install()
        self.recovery.commit()
        self.assertEqual(self.code.read_text(), 'new receiver')
        self.assertFalse(self.recovery.pending.exists())

    def test_next_run_recovers_an_interrupted_upgrade_before_snapshot(self):
        self.recovery.begin()
        self.change_install()
        next_setup = SimpleNamespace(BACKUPS=self.root / 'backups/upgrade-2',
                                     managed_runtime_processes=lambda: [])
        next_setup.BACKUPS.mkdir()
        later = installer.ConsoleRecovery('retropie', next_setup, self.paths)
        later.begin()
        self.assert_restored()
        later.commit()

    def test_corrupt_backup_blocks_restore_without_deleting_installed_files(self):
        self.recovery.begin()
        self.change_install()
        (self.recovery.backup / '0/receiver.py').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.recovery.restore()
        self.assertEqual(self.code.read_text(), 'new receiver')
        self.assertTrue(self.recovery.pending.exists())

    def test_service_restore_failure_retains_journal_for_retry(self):
        self.recovery.begin()
        self.change_install()
        self.restore_console_services.side_effect = OSError('service failed')
        with self.assertRaises(OSError):
            self.recovery.restore()
        self.assertTrue(self.recovery.pending.exists())
        self.restore_console_services.side_effect = None
        self.recovery.restore()
        self.assert_restored()

    def test_links_and_unmanaged_runtime_data_are_preserved(self):
        link = self.payload / 'helper'
        link.symlink_to('receiver.py')
        data = self.payload / 'data'
        data.mkdir()
        (data / 'live.json').write_text('before')
        self.recovery.begin()
        link.unlink()
        link.symlink_to('new-module.py')
        (data / 'live.json').write_text('after')
        self.recovery.restore()
        self.assertEqual(os.readlink(link), 'receiver.py')
        self.assertEqual((data / 'live.json').read_text(), 'after')

    def test_exception_and_interrupt_use_outer_transaction_recovery(self):
        for failure in (ValueError('validation failed'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(installer, 'console_recovery_paths', return_value=self.paths):
                    with self.assertRaises(type(failure)):
                        with installer.console_install_transaction('retropie', self.setup):
                            self.change_install()
                            raise failure
                self.assert_restored()
                # Each run uses a fresh backup, as the installer does.
                self.setup.BACKUPS = self.root / 'backups/upgrade-3'
                self.setup.BACKUPS.mkdir(exist_ok=True)
                self.recovery = installer.ConsoleRecovery('retropie', self.setup, self.paths)

    def test_cannot_start_concurrent_install(self):
        with patch.object(installer, 'console_recovery_paths', return_value=self.paths):
            with installer.console_install_transaction('retropie', self.setup):
                with self.assertRaises(BlockingIOError):
                    with installer.console_install_transaction('retropie', self.setup):
                        self.fail('A second installer must not run')

    def test_fresh_install_failure_removes_new_managed_files(self):
        self.recovery.paths = [self.new_file]
        self.recovery.begin()
        self.new_file.write_text('new service')
        self.recovery.restore()
        self.assertFalse(self.new_file.exists())

    def test_console_entrypoint_rolls_back_failed_checks_but_keeps_pairing_pending(self):
        for result in (1, 2):
            with self.subTest(result=result):
                self.setup.BACKUPS = self.root / ('backups/entry-' + str(result))
                archive = self.root / 'release.zip'
                import zipfile
                with zipfile.ZipFile(archive, 'w'):
                    pass
                report = SimpleNamespace(finish=lambda: result)
                self.setup.Report = lambda: report
                self.setup.install_retropie = lambda peer: self.change_install()
                self.setup.configure_games = lambda confirm: None
                for name in ("check_retropie", "check_unoq", "check_recalbox", "check_batocera"):
                    setattr(self.setup, name, lambda checked: None)
                with patch.object(installer, 'preflight'), \
                        patch.object(installer, 'unpack', return_value=ROOT), \
                        patch.object(installer, 'load_setup', return_value=self.setup), \
                        patch.object(installer, 'retropie_launcher_exists', return_value=True), \
                        patch.object(installer, 'console_recovery_paths', return_value=self.paths), \
                        patch.object(installer, 'rotate_console_backups'):
                    actual = installer.main(['retropie', '--archive', str(archive),
                                             '--version', 'test'])
                self.assertEqual(actual, result)
                if result == 1:
                    self.assert_restored()
                else:
                    self.assertEqual(self.code.read_text(), 'new receiver')
                self.assertFalse((self.setup.BACKUPS.parent / '.console-upgrade-pending.json').exists())

    def test_recalbox_and_batocera_recover_payload_and_saved_settings(self):
        for machine in ('recalbox', 'batocera'):
            with self.subTest(machine=machine):
                self.setup.BACKUPS = self.root / ('backups/' + machine)
                self.setup.BACKUPS.mkdir()
                recovery = installer.ConsoleRecovery(machine, self.setup, self.paths)
                recovery.begin()
                self.change_install()
                recovery.restore()
                self.assertEqual(self.code.read_text(), 'previous receiver')
                self.assertEqual(self.token.read_text(), 'private-pairing-value')
                self.restore_console_services.assert_called_with(machine, self.states)

    def test_non_systemd_restore_does_not_start_previously_stopped_runtime(self):
        for machine in ('batocera', 'recalbox'):
            with patch.object(installer.subprocess, 'run') as command:
                self.real_restore_services(machine, {'running': False})
                command.assert_not_called()

    def test_batocera_overlay_only_detaches_the_owned_mount(self):
        # Test the actual helper, separately from the platform-neutral transaction fixtures.
        actual = installer.mounted_router_generator
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'read_text', side_effect=[
                    '/usr/lib/configgen/libretroGenerator.py',
                    '1 2 0:1 /system/controller-router/libretroGenerator.py /usr/lib/configgen/libretroGenerator.py rw - ext4 /dev/test rw']):
            self.assertEqual(actual(), '/usr/lib/configgen/libretroGenerator.py')
        with patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'read_text', side_effect=[
                    '/usr/lib/configgen/libretroGenerator.py',
                    '1 2 0:1 /other-owner.py /usr/lib/configgen/libretroGenerator.py rw - ext4 /dev/test rw']):
            self.assertIsNone(actual())

    def test_restore_activation_keeps_inactive_units_stopped(self):
        with patch.object(installer.subprocess, 'run') as command:
            self.real_restore_services('retropie', self.states)
        starts = [call.args[0][-1] for call in command.call_args_list
                  if call.args[0][:2] == ['systemctl', 'start']]
        self.assertEqual(starts, ['virtualglove-controller-router.service',
                                  'virtualglove-receiver.service'])
        self.assertIn(['systemctl', 'disable', 'virtualglove-receiver.service'],
                      [call.args[0] for call in command.call_args_list])


if __name__ == '__main__':
    unittest.main()
