# Project: VirtualGlove
# File: tests/test_resolver.py
# Purpose: Verify local name resolution, cache refresh and safe failure behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-03 - Added resolver regression tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise Avahi protocol handling without requiring a running daemon."""
import socket
import unittest
from unittest.mock import patch
from virtualglove import resolver


class ResolverTests(unittest.TestCase):
    def setUp(self):
        resolver._cache.clear()

    @patch.object(resolver.Path, "exists", return_value=True)
    @patch.object(resolver.socket, "socket")
    @patch.object(resolver.time, "monotonic")
    def test_cache_refreshes_changed_address(self, clock, factory, exists):
        clock.side_effect = [1, 2, 7]
        channel = factory.return_value.__enter__.return_value
        channel.recv.side_effect = [b"+ 3 0 pi.local 192.0.2.1\n", b"+ 3 0 pi.local 192.0.2.2\n"]
        self.assertEqual(resolver.resolve_ipv4("pi.local"), "192.0.2.1")
        self.assertEqual(resolver.resolve_ipv4("pi.local"), "192.0.2.1")
        self.assertEqual(resolver.resolve_ipv4("pi.local"), "192.0.2.2")
        self.assertEqual(factory.call_count, 2)

    @patch.object(resolver.Path, "exists", return_value=True)
    @patch.object(resolver.socket, "socket")
    def test_bad_responses_are_not_cached(self, factory, exists):
        channel = factory.return_value.__enter__.return_value
        for response in (b"-15 Timeout\n", b"+ 3 0 wrong.local 192.0.2.1\n", b"+ 3 0 pi.local invalid\n"):
            channel.recv.return_value = response
            with self.assertRaises(socket.gaierror):
                resolver.resolve_ipv4("pi.local")
        self.assertFalse(resolver._cache)

    @patch.object(resolver.Path, "exists", return_value=False)
    @patch.object(resolver.socket, "gethostbyname", return_value="192.0.2.3")
    def test_normal_dns_without_avahi(self, lookup, exists):
        self.assertEqual(resolver.resolve_ipv4("pi.local"), "192.0.2.3")
        lookup.assert_called_once_with("pi.local")

class ResolverBridgeTests(unittest.TestCase):
    def test_bridge_rejects_nonlocal_and_multiple_commands(self):
        """The private bridge accepts only a single bounded .local query."""
        import runpy
        from pathlib import Path
        lookup = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/avahi-resolver-service.py'))['lookup']
        for query in (b'RESOLVE-HOSTNAME-IPV4 example.com\n', b'BROWSE-DNS-SERVERS\n',
                      b'RESOLVE-HOSTNAME-IPV4 pi.local\nOTHER\n'):
            with patch('socket.socket') as factory:
                self.assertTrue(lookup(query).startswith(b'-1'))
                factory.assert_not_called()

    def test_bridge_forwards_valid_query(self):
        """Forward Avahi replies without substituting a stale or pinned address."""
        import runpy
        from pathlib import Path
        lookup = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/avahi-resolver-service.py'))['lookup']
        with patch('socket.socket') as factory:
            channel = factory.return_value.__enter__.return_value
            channel.recv.return_value = b'+ 3 0 pi.local 192.0.2.5\n'
            self.assertEqual(lookup(b'RESOLVE-HOSTNAME-IPV4 pi.local\n'), channel.recv.return_value)
            channel.connect.assert_called_once_with('/run/avahi-daemon/socket')
