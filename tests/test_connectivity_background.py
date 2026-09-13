# Project: VirtualGlove
# File: tests/test_connectivity_background.py
# Purpose: Verify nonblocking address refresh and independent, fresh host Wi-Fi health.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Cover physical broadcasts and discovery during resolver failure.
#   2026-09-06 - Cover slow DNS, newest-state sends, stale answers, and Wi-Fi independence.

"""Exercise connectivity behavior without depending on a physical wireless device."""
import json
import runpy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from powerglove_vision.resolver import BackgroundAddress
from powerglove_vision.transport import UdpSender,decode_state
from powerglove_vision.controller_protocol import decode_message
from powerglove_vision.model import ControllerState
from powerglove_vision.wifi_status import (
    read_discovery_addresses, read_network_status, read_wifi_status,
)
from powerglove_vision.matrix import UnoQMatrix

ROOT=Path(__file__).resolve().parents[1]


class BackgroundTests(unittest.TestCase):
    def test_blocked_dns_does_not_block_send_or_replay_old_states(self):
        entered,release=threading.Event(),threading.Event()
        def slow(_host):
            entered.set();release.wait(2);return '192.0.2.4'
        with patch('powerglove_vision.transport.resolve_ipv4',side_effect=slow),patch('powerglove_vision.transport.socket.socket') as factory:
            sender=UdpSender('cabinet.local',55355,'test-token')
            try:
                factory.return_value.recvfrom.side_effect = BlockingIOError
                self.assertTrue(entered.wait(1))
                started=time.monotonic()
                for n in range(100):
                    self.assertFalse(sender.send(ControllerState.released(n,1,'off',True)))
                self.assertLess(time.monotonic()-started,.1)
                self.assertEqual(factory.return_value.sendto.call_count, 1)
                discovery = factory.return_value.sendto.call_args
                self.assertEqual(discovery[0][1], ('255.255.255.255', 55355))
                self.assertEqual(decode_message(discovery[0][0], 'test-token')['kind'], 'hello')
                release.set()
                deadline=time.monotonic()+1
                while sender.address.current()[0] is None and time.monotonic()<deadline:time.sleep(.005)
                factory.return_value.recvfrom.side_effect = BlockingIOError
                sender._peer = ('192.0.2.4',55355)
                sender.challenge = 'a'*32
                sender._hello_at = float('inf')
                self.assertTrue(sender.send(ControllerState.released(100,1,'off',True)))
                sent=factory.return_value.sendto.call_args[0]
                self.assertEqual(decode_message(sent[0],'test-token')['state']['sequence'],100)
                self.assertEqual(sent[1],('192.0.2.4',55355))
                self.assertEqual(factory.return_value.sendto.call_count,2)
            finally:release.set();sender.close()

    def test_refresh_changes_address_and_stale_failure_expires(self):
        second=threading.Event()
        count=[0]
        def resolve(_host):
            count[0]+=1
            if count[0]==1:return '192.0.2.1'
            second.set();return '192.0.2.2'
        address=BackgroundAddress('cabinet.local',resolve=resolve,refresh_seconds=.01)
        try:
            self.assertTrue(second.wait(1))
            deadline=time.monotonic()+1
            while address.current()[0]!='192.0.2.2' and time.monotonic()<deadline:time.sleep(.005)
            self.assertEqual(address.current()[0],'192.0.2.2')
            address.close()
            address.thread.join(1)
            with address.lock:address.expires=time.monotonic()-1
            self.assertIsNone(address.current()[0])
        finally:address.close()

    def test_literal_address_needs_no_background_lookup(self):
        resolver=Mock()
        address=BackgroundAddress('192.0.2.8',resolve=resolver)
        self.assertEqual(address.current()[0],'192.0.2.8')
        self.assertIsNone(address.thread)
        resolver.assert_not_called()


class WifiTests(unittest.TestCase):
    def test_network_includes_usb_ethernet_but_not_virtual_interfaces(self):
        read=runpy.run_path(str(ROOT/'uno-q/virtualglove-wifi-status.py'))['link_state']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('lo','docker0','veth123'):
                dev=root/name;dev.mkdir();(dev/'type').write_text('1');(dev/'carrier').write_text('1')
            self.assertEqual(read(root),'unavailable')
            eth=root/'enx123';eth.mkdir();(eth/'device').mkdir();(eth/'type').write_text('1');(eth/'carrier').write_text('1')
            self.assertEqual(read(root),'connected')
            wifi=root/'wlan0';wifi.mkdir();(wifi/'wireless').mkdir();(wifi/'carrier').write_text('0')
            self.assertEqual(read(root),'connected')
            (eth/'carrier').write_text('0');self.assertEqual(read(root),'disconnected')
            (eth/'carrier').unlink();self.assertEqual(read(root),'unavailable')
            (wifi/'carrier').write_text('1');self.assertEqual(read(root),'connected')

    def test_network_reader_handles_old_and_fresh_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'status.json'
            with patch('powerglove_vision.wifi_status.time.time',return_value=100):
                for value,expected in [({'state':'connected'},'connected'),({'state':'disconnected'},'unavailable'),({'state':'disconnected','networking':'connected'},'connected'),({'networking':'disconnected'},'disconnected'),({'networking':'invalid'},'unavailable')]:
                    path.write_text(json.dumps(dict(version=1,observed_at=100,**value)))
                    self.assertEqual(read_network_status(path),expected)
                for stamp in (84,101):
                    path.write_text(json.dumps(dict(version=1,observed_at=stamp,networking='connected')))
                    self.assertEqual(read_network_status(path),'unavailable')

    def test_host_reads_only_wireless_carrier(self):
        read=runpy.run_path(str(ROOT/'uno-q/virtualglove-wifi-status.py'))['wifi_state']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ethernet=root/'eth0';ethernet.mkdir();(ethernet/'carrier').write_text('1')
            self.assertEqual(read(root),'unavailable')
            wifi=root/'wlan0';wifi.mkdir();(wifi/'wireless').mkdir();(wifi/'carrier').write_text('0')
            self.assertEqual(read(root),'disconnected')
            (wifi/'carrier').write_text('1')
            self.assertEqual(read(root),'connected')
            (wifi/'carrier').unlink();(wifi/'operstate').write_text('down')
            self.assertEqual(read(root),'disconnected')

    def test_host_reports_broadcasts_only_for_connected_physical_links(self):
        broadcasts=runpy.run_path(str(ROOT/'uno-q/virtualglove-wifi-status.py'))['broadcast_addresses']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            wifi=root/'wlan0';wifi.mkdir();(wifi/'wireless').mkdir();(wifi/'carrier').write_text('1')
            ethernet=root/'enx1';ethernet.mkdir();(ethernet/'device').mkdir();(ethernet/'type').write_text('1');(ethernet/'carrier').write_text('1')
            bridge=root/'docker0';bridge.mkdir();(bridge/'carrier').write_text('1')
            lookup=lambda name:{'wlan0':('10.0.2.96','255.255.255.0'),
                                'enx1':('192.168.50.4','255.255.255.0')}[name]
            self.assertEqual(broadcasts(root,lookup),['10.0.2.255','192.168.50.255'])
            (ethernet/'carrier').write_text('0')
            self.assertEqual(broadcasts(root,lookup),['10.0.2.255'])

    def test_app_rejects_stale_future_and_missing_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wifi.json'
            self.assertEqual(read_wifi_status(path),'unavailable')
            for delta,expected in [(0,'connected'),(-16,'unavailable'),(5,'unavailable')]:
                path.write_text(json.dumps({'version':1,'state':'connected','observed_at':100+delta}))
                with patch('powerglove_vision.wifi_status.time.time',return_value=100):
                    self.assertEqual(read_wifi_status(path),expected)

    def test_app_accepts_only_fresh_bounded_discovery_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'status.json'
            with patch('powerglove_vision.wifi_status.time.time',return_value=100):
                path.write_text(json.dumps({'version':2,'observed_at':100,
                    'broadcasts':['10.0.2.255','192.168.50.255','10.0.2.255']}))
                self.assertEqual(read_discovery_addresses(path),('10.0.2.255','192.168.50.255'))
                path.write_text(json.dumps({'version':2,'observed_at':80,
                    'broadcasts':['10.0.2.255']}))
                self.assertEqual(read_discovery_addresses(path),())
                path.write_text(json.dumps({'version':2,'observed_at':100,
                    'broadcasts':['224.0.0.1']}))
                self.assertEqual(read_discovery_addresses(path),())

    def test_network_pixel_does_not_depend_on_console(self):
        calls=[];matrix=UnoQMatrix(call=lambda *args:calls.append(args))
        with patch('powerglove_vision.wifi_status.read_network_status',return_value='connected'):
            matrix.set_attract({'matrix_attract':'off'},idle=False)
        self.assertEqual(calls[-1],('set_virtualglove_attract',2,4))
        with patch('powerglove_vision.wifi_status.read_network_status',return_value='disconnected'):
            matrix.set_attract({'matrix_attract':'off'},idle=False)
        self.assertEqual(calls[-1],('set_virtualglove_attract',2,0))
