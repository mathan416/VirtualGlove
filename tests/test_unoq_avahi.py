# Project: VirtualGlove
# File: tests/test_unoq_avahi.py
# Purpose: Verify Controller mDNS is restricted to physical interfaces.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added physical-interface Avahi configuration coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify Controller mDNS is restricted to physical interfaces."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('avahi_config',Path(__file__).resolve().parents[1]/'scripts/configure-uno-q-avahi.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class AvahiTests(unittest.TestCase):
    def test_only_server_allowlist_changes_and_is_idempotent(self):
        source='[server]\nuse-ipv6=yes\nallow-interfaces=docker0\n[publish]\npublish-workstation=no\n'
        updated=m.configure_text(source,['wlan0','enx123'])
        self.assertIn('allow-interfaces=enx123,wlan0',updated)
        self.assertNotIn('docker0',updated)
        self.assertIn('use-ipv6=yes',updated)
        self.assertTrue(updated.endswith('[publish]\npublish-workstation=no\n'))
        self.assertEqual(updated,m.configure_text(updated,['wlan0','enx123']))
    def test_no_hardware_or_invalid_name_does_not_silently_publish_all(self):
        for names in ([],['eth0\nuse-ipv6=no'],['a'*16]):
            with self.assertRaises(ValueError):m.configure_text('[server]\n',names)
    def test_backup_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'avahi-daemon.conf';p.write_text('[server]\n')
            self.assertTrue(m.configure(p,['wlan0']))
            self.assertFalse(m.configure(p,['wlan0']))
            m.configure(p,['wlan0','eth0'])
            self.assertEqual(p.with_name(p.name+'.virtualglove-backup').read_text(),'[server]\n')
    def test_physical_interface_selection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('wlan0','enx123','docker0','veth1','lo'):(root/name).mkdir()
            for name in ('wlan0','enx123'):(root/name/'device').mkdir()
            self.assertEqual(m.physical_interfaces(root),['enx123','wlan0'])

if __name__=='__main__':unittest.main()
