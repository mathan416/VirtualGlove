# Project: VirtualGlove
# File: tests/test_transport.py
# Purpose: Verify controller packet protocol validation and sender recovery from network failures.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Cover stale-address liveness and authenticated peer recovery.
#   2026-09-09 - Covered state-first maintenance and bounded reply processing.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-05 - Verified native compound hand poses survive transport.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.

"""Verify controller packet protocol validation and sender recovery from network failures."""

import unittest
from socket import gaierror
from unittest.mock import Mock, patch

from virtualglove.model import ControllerState
from virtualglove.controller_protocol import decode_message, encode_message
from virtualglove.transport import (
    DISCOVERY_ADDRESS, UdpSender, validate_state,
)


class TransportTests(unittest.TestCase):
    def setUp(self):
        resolver = patch("virtualglove.transport.resolve_ipv4", return_value="192.0.2.1")
        resolver.start()
        self.addCleanup(resolver.stop)

    @patch("virtualglove.transport.resolve_ipv4")
    @patch("virtualglove.transport.socket.socket")
    def test_blank_destination_never_resolves_or_sends(self, socket_factory, resolver):
        """Local practice cannot accidentally send to an implicit network destination."""
        sender = UdpSender("", 55355, "secret")
        self.assertFalse(sender.send(ControllerState.released(1, 1.0, "off", False)))
        resolver.assert_not_called()
        socket_factory.return_value.sendto.assert_not_called()
        self.assertIn("Connection", sender.last_error)

    def test_signed_state_validation(self):
        state = ControllerState.released(7, 1.5, "bad_street_brawler", True)
        state.buttons.update({"closed_hand": True, "index_point": True})
        decoded = validate_state(state.to_transport_dict())
        self.assertEqual(decoded["sequence"], 7)
        self.assertTrue(decoded["buttons"]["closed_hand"])
        self.assertTrue(decoded["buttons"]["index_point"])

    def test_transport_envelope_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_state(dict(
                ControllerState.released(1, 1.0, "off").to_transport_dict(),
                protocol="virtualglove-vision/1",
            ))

    @patch("virtualglove.transport.socket.socket")
    def test_temporary_name_failure_does_not_stop_sender(self, socket_factory):
        udp_socket = Mock()
        udp_socket.recvfrom.side_effect = BlockingIOError
        udp_socket.sendto.side_effect = gaierror(-2, "Name or service not known")
        socket_factory.return_value = udp_socket
        sender = UdpSender("192.0.2.1", 55355, "secret")
        self.addCleanup(sender.close)
        state = ControllerState.released(1, 1.0, "bad_street_brawler", True)

        self.assertFalse(sender.send(state))
        self.assertIn("Name or service not known", sender.last_error)
        self.assertFalse(sender.send(state))
        udp_socket.sendto.assert_called_once()

    @patch("virtualglove.transport.socket.socket")
    def test_successful_send_reports_receiver_available(self, socket_factory):
        sender = UdpSender("192.0.2.1", 55355, "secret")
        self.addCleanup(sender.close)
        socket_factory.return_value.recvfrom.side_effect = BlockingIOError
        sender._peer = ("192.0.2.1",55355)
        sender.challenge = "a" * 32
        sender._hello_at = float("inf")
        state = ControllerState.released(1, 1.0, "bad_street_brawler", True)

        self.assertTrue(sender.send(state))
        self.assertIsNone(sender.last_error)
        self.assertEqual(sender.active_address, "192.0.2.1")

    @patch("virtualglove.transport.socket.socket")
    def test_established_state_precedes_due_maintenance_hello(self, socket_factory):
        sender = UdpSender("192.0.2.1", 55355, "secret")
        self.addCleanup(sender.close)
        udp_socket = socket_factory.return_value
        udp_socket.recvfrom.side_effect = BlockingIOError
        sender._peer = ("192.0.2.1", 55355)
        sender.challenge = "a" * 32
        sender._hello_at = 0.0

        self.assertTrue(sender.send(ControllerState.released(1, 1.0, "off", True)))
        kinds = [decode_message(call[0][0], "secret")["kind"]
                 for call in udp_socket.sendto.call_args_list]
        self.assertEqual(kinds, ["state", "hello"])

    @patch("virtualglove.transport.time.monotonic", return_value=10.0)
    @patch("virtualglove.transport.socket.socket")
    def test_stale_literal_address_discovers_only_authenticated_receiver(self, socket_factory, _clock):
        udp_socket = socket_factory.return_value
        udp_socket.recvfrom.side_effect = BlockingIOError
        sender = UdpSender("192.0.2.10", 55355, "secret")
        self.addCleanup(sender.close)
        sender._peer = ("192.0.2.10", 55355)
        sender.challenge = "a" * 32
        sender._last_reply_at = 1.0
        sender._hello_at = 0.0

        state = ControllerState.released(1, 1.0, "off", True)
        self.assertFalse(sender.send(state))
        destinations = [call[0][1] for call in udp_socket.sendto.call_args_list]
        self.assertIn(("192.0.2.10", 55355), destinations)
        self.assertIn((DISCOVERY_ADDRESS, 55355), destinations)
        self.assertTrue(all(decode_message(call[0][0], "secret")["kind"] == "hello"
                            for call in udp_socket.sendto.call_args_list))

        reply = encode_message(
            "challenge", "secret", session=sender.session,
            request=sender.request, challenge="b" * 32,
        )
        udp_socket.reset_mock()
        udp_socket.recvfrom.side_effect = [
            (reply, ("192.0.2.44", 55355)), BlockingIOError(),
        ]
        self.assertTrue(sender.send(ControllerState.released(2, 1.0, "off", True)))
        sent = [(decode_message(call[0][0], "secret")["kind"], call[0][1])
                for call in udp_socket.sendto.call_args_list]
        self.assertIn(("state", ("192.0.2.44", 55355)), sent)
        self.assertEqual(sender._peer, ("192.0.2.44", 55355))

    @patch("virtualglove.transport.socket.socket")
    def test_missing_hostname_resolution_starts_authenticated_discovery(self, socket_factory):
        udp_socket = socket_factory.return_value
        udp_socket.recvfrom.side_effect = BlockingIOError
        sender = UdpSender("cabinet.local", 55355, "secret")
        self.addCleanup(sender.close)
        sender.address.close()
        sender.address = Mock()
        sender.address.current.return_value = (None, "name unavailable")

        self.assertFalse(sender.send(ControllerState.released(1, 1.0, "off", True)))
        payload, destination = udp_socket.sendto.call_args[0]
        self.assertEqual(destination, (DISCOVERY_ADDRESS, 55355))
        self.assertEqual(decode_message(payload, "secret")["kind"], "hello")
        self.assertIn("Looking for", sender.last_error)

    @patch("virtualglove.transport.decode_message", side_effect=ValueError("junk"))
    @patch("virtualglove.transport.socket.socket")
    def test_handshake_reply_work_is_bounded_per_frame(self, socket_factory, decode):
        sender = UdpSender("192.0.2.1", 55355, "secret")
        self.addCleanup(sender.close)
        udp_socket = socket_factory.return_value
        udp_socket.recvfrom.return_value = (b"junk", ("192.0.2.1", 55355))
        sender._peer = ("192.0.2.1", 55355)
        sender._hello_at = float("inf")

        self.assertFalse(sender.send(ControllerState.released(1, 1.0, "off", True)))
        self.assertEqual(decode.call_count, 2)

    def test_transport_mapping_preserves_wire_fields_without_recursive_copy(self):
        state = ControllerState.released(7, 1.5, "super_glove_ball", True)
        wire = state.to_transport_dict()
        self.assertNotIn("protocol", wire)
        self.assertEqual(wire["sequence"], 7)
        self.assertIs(wire["axes"], state.axes)
        decoded = decode_message(encode_message(
            "state", "secret", session="a" * 32,
            challenge="b" * 32, state=wire,
        ), "secret")
        self.assertEqual(decoded["state"]["profile"], "super_glove_ball")


if __name__ == "__main__":
    unittest.main()
