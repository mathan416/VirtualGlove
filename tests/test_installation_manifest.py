# Project: VirtualGlove
# File: tests/test_installation_manifest.py
# Purpose: Verify owned-file cleanup, local change preservation, and interrupted update recovery.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added installation inventory regression coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise actual filesystem updates inside isolated temporary installation roots."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts/installation-manifest.py'


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.source=self.base/'release';self.root=self.base/'app'
        self.source.mkdir();self.root.mkdir();self.module=runpy.run_path(str(MODULE));self.g=self.module['apply'].__globals__
        self.count=0

    def put(self,name,text,root=None):
        path=(root or self.source)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return path

    def apply(self):
        self.count+=1
        return self.module['apply'](self.source,self.root,self.base/('backup'+str(self.count)))

    def test_baseline_never_guesses_obsolete_unknown_files(self):
        self.put('old-unknown.txt','keep',self.root);self.put('src/a.py','release')
        self.put('config/profiles.json','defaults');self.put('config/profiles.json','personal',self.root)
        self.apply()
        self.assertEqual((self.root/'old-unknown.txt').read_text(),'keep')
        self.assertEqual((self.root/'config/profiles.json').read_text(),'defaults')
        manifest=self.module['read_manifest'](self.root)
        self.assertIn('config/profiles.json',manifest['files'])
        self.assertNotIn('old-unknown.txt',manifest['files'])

    def test_upgrade_prunes_unchanged_files_and_backs_them_up(self):
        self.put('src/old.py','old');self.put('src/current.py','one');self.apply()
        (self.source/'src/old.py').unlink();self.put('src/current.py','two');result=self.apply()
        self.assertEqual(result['removed'],['src/old.py'])
        self.assertFalse((self.root/'src/old.py').exists())
        self.assertEqual((self.base/'backup2/src/old.py').read_text(),'old')
        self.assertEqual((self.base/'backup2/src/current.py').read_text(),'one')
        self.assertEqual(self.module['check'](self.root),[])
        before=(self.root/self.module['MANIFEST']).stat().st_mtime_ns
        self.apply()
        self.assertEqual(before,(self.root/self.module['MANIFEST']).stat().st_mtime_ns)

    def test_legacy_manifest_is_migrated_and_renamed_files_are_pruned(self):
        self.put('uno-q/powerglove-helper.service','old');self.apply()
        (self.root/self.module['MANIFEST']).rename(self.root/self.module['LEGACY_MANIFEST'])
        (self.root/self.module['LOCK']).rename(self.root/self.module['LEGACY_LOCK'])
        (self.source/'uno-q/powerglove-helper.service').unlink()
        self.put('uno-q/virtualglove-helper.service','new')
        result=self.apply()
        self.assertEqual(result['removed'],['uno-q/powerglove-helper.service'])
        self.assertFalse((self.root/'uno-q/powerglove-helper.service').exists())
        self.assertEqual((self.root/'uno-q/virtualglove-helper.service').read_text(),'new')
        self.assertTrue((self.root/self.module['MANIFEST']).is_file())
        self.assertFalse((self.root/self.module['LEGACY_MANIFEST']).exists())
        self.assertFalse((self.root/self.module['LEGACY_LOCK']).exists())

    def test_modified_and_mode_changed_files_stay_owned_but_are_never_pruned(self):
        for name in ('src/old.py','src/current.py','src/mode.py'):self.put(name,'original')
        self.apply();self.put('src/old.py','custom',self.root);self.put('src/current.py','custom',self.root)
        (self.root/'src/mode.py').chmod(0o755)
        (self.source/'src/old.py').unlink();(self.source/'src/mode.py').unlink();self.put('src/current.py','new release')
        self.assertEqual(set(self.apply()['preserved']),{'src/old.py','src/current.py','src/mode.py'})
        self.apply()
        self.assertEqual((self.root/'src/old.py').read_text(),'custom')
        self.assertEqual(len(self.module['check'](self.root)),3)

    def test_invalid_manifest_and_symlinks_fail_before_changing_payload(self):
        self.put('src/a.py','one');self.apply();self.put('src/a.py','two')
        manifest=self.root/self.module['MANIFEST'];original=manifest.read_text()
        for name in ('../escape','data/token','/etc/passwd','.virtualglove-install.json','docs/cheatsheet.md'):
            value=json.loads(original);value['files'][name]=next(iter(value['files'].values()));manifest.write_text(json.dumps(value))
            with self.assertRaises(ValueError):self.apply()
            self.assertEqual((self.root/'src/a.py').read_text(),'one')
        manifest.write_text(original)
        (self.root/'src/a.py').unlink();(self.root/'src/a.py').symlink_to(self.source/'src/a.py')
        with self.assertRaises(ValueError):self.apply()

    def test_failure_restores_deletions_replacements_new_files_and_manifest(self):
        self.put('src/old.py','old');self.put('src/a.py','one');self.apply()
        before=(self.root/self.module['MANIFEST']).read_bytes()
        (self.source/'src/old.py').unlink();self.put('src/a.py','two');self.put('src/new.py','new')
        real=self.g['atomic'];failed=[False]
        def fail(path,*args):
            if path==self.root/self.module['MANIFEST'] and not failed[0]:
                failed[0]=True;raise OSError('simulated write failure')
            return real(path,*args)
        with patch.dict(self.g,atomic=fail):
            with self.assertRaises(OSError):self.apply()
        self.assertEqual((self.root/'src/old.py').read_text(),'old')
        self.assertEqual((self.root/'src/a.py').read_text(),'one')
        self.assertFalse((self.root/'src/new.py').exists())
        self.assertEqual((self.root/self.module['MANIFEST']).read_bytes(),before)
        self.assertFalse((self.root/self.module['JOURNAL']).exists())

    def test_interruption_journal_blocks_update_until_recovered(self):
        self.put('src/a.py','one');self.apply();self.put('src/a.py','two')
        real=self.g['atomic']
        def fail(path,*args):
            if path==self.root/self.module['MANIFEST']:raise OSError('interrupted commit')
            return real(path,*args)
        with patch.dict(self.g,atomic=fail,rollback=lambda root:None):
            with self.assertRaises(OSError):self.apply()
        self.assertTrue(any('Interrupted' in x for x in self.module['check'](self.root)))
        with self.assertRaisesRegex(ValueError,'recover'):self.apply()
        with self.module['locked'](self.root):self.module['rollback'](self.root)
        self.assertEqual((self.root/'src/a.py').read_text(),'one')
        self.assertEqual(self.module['check'](self.root),[])
        self.apply();self.assertEqual((self.root/'src/a.py').read_text(),'two')

    def test_read_only_check_does_not_create_a_manifest_or_lock(self):
        before=list(self.root.iterdir());self.assertTrue(self.module['check'](self.root))
        self.assertEqual(list(self.root.iterdir()),before)

    def test_concurrent_writer_is_rejected(self):
        self.put('src/a.py','one')
        with self.module['locked'](self.root):
            with self.assertRaises(BlockingIOError):self.apply()
        self.assertFalse((self.root/'src/a.py').exists())

    def test_source_symlink_directory_is_rejected_without_deleting_owned_files(self):
        self.put('src/a.py','one');self.apply()
        (self.source/'src/a.py').unlink()
        (self.source/'link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual((self.root/'src/a.py').read_text(),'one')

    def test_changed_release_and_new_settings_roll_back_before_manifest_commit(self):
        self.put('src/a.py','one');self.apply()
        self.put('src/a.py','two');self.put('config/profiles.json','defaults')
        real=self.g['atomic'];changed=[False]
        def change_source(path,*args):
            result=real(path,*args)
            if path==self.root/self.module['JOURNAL'] and not changed[0]:
                changed[0]=True;self.put('src/a.py','changed after validation')
            return result
        with patch.dict(self.g,atomic=change_source):
            with self.assertRaisesRegex(ValueError,'Release changed'):self.apply()
        self.assertEqual((self.root/'src/a.py').read_text(),'one')
        self.assertFalse((self.root/'config/profiles.json').exists())
        self.assertEqual(self.module['check'](self.root),[])

    def test_release_profiles_replace_local_copy_and_are_backed_up(self):
        self.put('config/profiles.json','one');self.apply()
        self.put('config/profiles.json','local',self.root);self.put('config/profiles.json','two')
        self.apply()
        self.assertEqual((self.root/'config/profiles.json').read_text(),'two')
        self.assertEqual((self.base/'backup2/config/profiles.json').read_text(),'local')
