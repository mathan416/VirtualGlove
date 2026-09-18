# Project: VirtualGlove
# File: tests/test_controller_protocol.py
# Purpose: Verify signed controller authentication, replay rejection, and restart recovery.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Verify native Super Glove Ball publication precedes uinput.
#   2026-09-06 - Exercise version-two sessions over deterministic and real UDP paths.
# Full history: docs/CHANGELOG.md and Git history.

"""Protect live input admission without relying on clocks shared by the two hosts."""
import json
import socket
import select
import sys
import subprocess
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from powerglove_vision import receiver

from powerglove_vision.controller_protocol import ReceiverSessions, encode_message, decode_message
from powerglove_vision.transport import UdpSender
from powerglove_vision.model import ControllerState

TOKEN = 'private-test-controller-secret'
PEER = ('127.0.0.1',12345)


def hello(session, request='b'*32):
    return encode_message('hello', TOKEN, session=session, request=request)


def state_packet(session, challenge, sequence=1, **fields):
    state = ControllerState.released(sequence,1,'super_glove_ball',True).to_transport_dict()
    state.update(fields)
    return encode_message('state',TOKEN,session=session,challenge=challenge,state=state)


def handshake(receiver, session):
    state,reply=receiver.receive(hello(session),PEER)
    assert state is None
    return decode_message(reply,TOKEN)['challenge']


class SignedControllerTests(unittest.TestCase):
    def test_secret_absent_and_every_field_authenticated(self):
        packet=hello('a'*32)
        self.assertNotIn(TOKEN.encode(),packet)
        for key,value in [('session','c'*32),('kind','state'),('request','d'*32)]:
            data=json.loads(packet);data[key]=value
            with self.assertRaises(ValueError):decode_message(json.dumps(data).encode(),TOKEN)
        with self.assertRaises(ValueError):decode_message(packet,'other-token')
        with self.assertRaises(ValueError):decode_message(packet[:-1]+b',"kind":"hello"}',TOKEN)
        with self.assertRaises(ValueError):decode_message(b'x'*4097,TOKEN)

    def test_old_sessions_and_receiver_restarts_reject_recordings(self):
        receiver=ReceiverSessions(TOKEN)
        first='a'*32;second='c'*32
        challenge=handshake(receiver,first)
        packet=state_packet(first,challenge,5,axes={'x':123,'y':-321},buttons={'closed_hand':True,'index_point':True})
        state,_=receiver.receive(packet,PEER)
        self.assertEqual(state['axes'],{'x':123,'y':-321})
        self.assertTrue(state['buttons']['index_point'])
        self.assertIsNone(receiver.receive(packet,PEER)[0])
        self.assertIsNone(receiver.receive(state_packet(first,challenge,4),PEER)[0])
        new=handshake(receiver,second)
        self.assertIsNotNone(receiver.receive(state_packet(second,new),PEER)[0])
        self.assertIsNone(receiver.receive(state_packet(first,challenge,100),PEER)[0])
        # Replaying even the old authenticated hello cannot resurrect its challenge.
        self.assertNotEqual(handshake(receiver,first),challenge)
        self.assertIsNone(receiver.receive(packet,PEER)[0])
        reboot=ReceiverSessions(TOKEN)
        self.assertIsNone(reboot.receive(packet,PEER)[0])
        self.assertNotEqual(handshake(reboot,first),challenge)
        self.assertIsNone(reboot.receive(packet,PEER)[0])

    def test_pending_sessions_expire_are_bounded_and_cannot_replace_newer_input(self):
        now=[0.];receiver=ReceiverSessions(TOKEN,clock=lambda:now[0])
        old=handshake(receiver,'a'*32)
        new=handshake(receiver,'c'*32)
        receiver.receive(state_packet('c'*32,new),PEER)
        self.assertIsNone(receiver.receive(state_packet('a'*32,old),PEER)[0])
        for n in range(20):receiver.receive(hello(format(n,'032x')),PEER)
        self.assertEqual(len(receiver.pending),8)
        now[0]=4
        self.assertIsNone(receiver.receive(state_packet('a'*32,old),PEER)[0])
        self.assertFalse(receiver.pending)
        self.assertIsNotNone(receiver.receive(state_packet('c'*32,new,2),PEER)[0])

    def test_invalid_state_does_not_advance_sequence_or_activate_session(self):
        receiver=ReceiverSessions(TOKEN);session='a'*32;challenge=handshake(receiver,session)
        for fields in ({'axes':{'x':999999}}, {'buttons':{'a':1}}, {'token':'secret'}):
            with self.assertRaises(ValueError):receiver.receive(state_packet(session,challenge,100,**fields),PEER)
        self.assertIsNone(receiver.active)
        self.assertIsNotNone(receiver.receive(state_packet(session,challenge,1),PEER)[0])
        self.assertIsNone(receiver.receive(state_packet(session,challenge,2),('127.0.0.2',12345))[0])

    def test_real_udp_sender_drops_handshake_frames_and_recovers_restart(self):
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0));server.settimeout(.2)
        self.addCleanup(server.close)
        sender=UdpSender('127.0.0.1',server.getsockname()[1],TOKEN);self.addCleanup(sender.close)
        receiver=ReceiverSessions(TOKEN)
        def pump():
            payload,peer=server.recvfrom(4097)
            state,reply=receiver.receive(payload,peer)
            if reply:
                server.sendto(reply,peer)
                self.assertTrue(select.select([sender.socket],[],[],.2)[0])
            return state
        self.assertFalse(sender.send(ControllerState.released(1,1,'off')))
        self.assertIsNone(pump())
        self.assertTrue(sender.send(ControllerState.released(2,1,'off')))
        self.assertEqual(pump()['sequence'],2)
        receiver=ReceiverSessions(TOKEN)
        self.assertTrue(sender.send(ControllerState.released(3,1,'off')))
        self.assertIsNone(pump())
        sender._hello_at=0
        sender.send(ControllerState.released(4,1,'off'))
        self.assertIsNone(pump());self.assertIsNone(pump())
        sender.send(ControllerState.released(5,1,'off'))
        self.assertEqual(pump()['sequence'],5)
        sender.new_session()
        self.assertFalse(sender.send(ControllerState.released(0,1,'off')))
        self.assertIsNone(pump())
        sender.send(ControllerState.released(1,1,'off'))
        self.assertEqual(pump()['sequence'],1)

    def test_unsigned_v1_packets_are_rejected_and_flag_is_removed(self):
        legacy=json.dumps(dict(protocol='virtualglove-vision/1',token=TOKEN,
                               session='legacy',sequence=1)).encode()
        sock,native=Mock(),Mock()
        sock.recvfrom.side_effect=[(legacy,PEER),KeyboardInterrupt()]
        sock.recvmsg.side_effect=lambda size,space:(lambda pair:(pair[0],[],0,pair[1]))(sock.recvfrom(size))
        device_factory=Mock()
        with patch.object(receiver.socket,'socket',return_value=sock), \
                patch.object(receiver,'UInputDevice',device_factory), \
                patch.object(receiver,'NativeStateWriter',return_value=native), \
                patch('sys.argv',['receiver','--token',TOKEN]):
            self.assertEqual(receiver.main(),0)
        device_factory.assert_not_called()
        with self.assertRaises(SystemExit):
            receiver.build_parser().parse_args([
                '--token', TOKEN, '--allow-legacy-controller'
            ])

    def test_handshakes_do_not_extend_the_release_deadline(self):
        now=[0.];sessions=ReceiverSessions(TOKEN,clock=lambda:now[0]);session='a'*32
        challenge=handshake(sessions,session)
        packets=iter([state_packet(session,challenge)]+[hello(session)]*6)
        sock,device,native=Mock(),Mock(),Mock();released=[]
        def receive(_):
            now[0]+=.1
            try:return next(packets),PEER
            except StopIteration:raise KeyboardInterrupt
        sock.recvfrom.side_effect=receive
        sock.recvmsg.side_effect=lambda size,space:(lambda pair:(pair[0],[],0,pair[1]))(sock.recvfrom(size))
        device.release.side_effect=lambda:released.append(now[0])
        with patch.object(receiver,'ReceiverSessions',return_value=sessions), patch.object(receiver.time,'monotonic',side_effect=lambda:now[0]), patch.object(receiver.socket,'socket',return_value=sock), patch.object(receiver,'UInputDevice',return_value=device), patch.object(receiver,'NativeStateWriter',return_value=native), patch('sys.argv',['receiver','--token',TOKEN]):
            self.assertEqual(receiver.main(),0)
        self.assertEqual(device.write_state.call_count,1)
        self.assertLessEqual(released[0],.4)
        native.release.assert_any_call(2)

    def test_native_profile_is_published_before_virtual_gamepad(self):
        events = []
        sessions = ReceiverSessions(TOKEN)
        session = 'a' * 32
        challenge = handshake(sessions, session)
        packet = state_packet(session, challenge)
        sock, device, native = Mock(), Mock(), Mock()
        sock.recvfrom.side_effect = [
            (packet, PEER), KeyboardInterrupt(),
        ]
        sock.recvmsg.side_effect = lambda size, space: (
            lambda pair: (pair[0], [], 0, pair[1])
        )(sock.recvfrom(size))
        native.write.side_effect = lambda _state: events.append('native')
        device.write_state.side_effect = lambda _state: events.append('gamepad')
        with patch.object(receiver, 'ReceiverSessions', return_value=sessions), \
                patch.object(receiver.socket, 'socket', return_value=sock), \
                patch.object(receiver, 'UInputDevice', return_value=device), \
                patch.object(receiver, 'NativeStateWriter', return_value=native), \
                patch('sys.argv', ['receiver', '--token', TOKEN]):
            self.assertEqual(receiver.main(), 0)
        self.assertEqual(events, ['native', 'gamepad'])

    def test_windows_native_profile_bypasses_keyboard_injection(self):
        sessions = ReceiverSessions(TOKEN)
        session = 'a' * 32
        challenge = handshake(sessions, session)
        packet = state_packet(
            session, challenge, buttons={"start": True},
        )
        sock, native = Mock(), Mock()
        sock.recvfrom.side_effect = [(packet, PEER), KeyboardInterrupt()]
        sock.recvmsg.side_effect = lambda size, space: (
            lambda pair: (pair[0], [], 0, pair[1])
        )(sock.recvfrom(size))
        with patch.object(receiver, 'ReceiverSessions', return_value=sessions), \
                patch.object(receiver.socket, 'socket', return_value=sock), \
                patch.object(receiver, 'NativeStateWriter', return_value=native), \
                patch('powerglove_vision.windows_input.WindowsKeyboardDevice') as keyboard, \
                patch('sys.argv', [
                    'receiver', '--token', TOKEN,
                    '--output-device', 'windows-keyboard',
                ]):
            self.assertEqual(receiver.main(), 0)
        keyboard.assert_not_called()
        native.write.assert_called_once()
        self.assertTrue(native.write.call_args.args[0]['buttons']['start'])

    def test_windows_native_profile_stays_out_of_keyboard_when_record_unavailable(self):
        sessions = ReceiverSessions(TOKEN)
        session = 'a' * 32
        challenge = handshake(sessions, session)
        packet = state_packet(session, challenge, buttons={"start": True})
        sock = Mock()
        sock.recvfrom.side_effect = [(packet, PEER), KeyboardInterrupt()]
        sock.recvmsg.side_effect = lambda size, space: (
            lambda pair: (pair[0], [], 0, pair[1])
        )(sock.recvfrom(size))
        with patch.object(receiver, 'ReceiverSessions', return_value=sessions), \
                patch.object(receiver.socket, 'socket', return_value=sock), \
                patch.object(receiver, 'NativeStateWriter', side_effect=OSError('unavailable')), \
                patch('powerglove_vision.windows_input.WindowsKeyboardDevice') as keyboard, \
                patch('sys.argv', [
                    'receiver', '--token', TOKEN,
                    '--output-device', 'windows-keyboard',
                ]):
            self.assertEqual(receiver.main(), 0)
        keyboard.assert_not_called()

    def test_multihomed_reply_requires_port_signature_and_fresh_request(self):
        for mode in ('valid','wrong-port','wrong-request','wrong-key'):
            sock=Mock()
            with patch('powerglove_vision.transport.socket.socket',return_value=sock):
                sender=UdpSender('192.0.2.52',55355,TOKEN)
            self.addCleanup(sender.close)
            sender._peer=('192.0.2.52',55355);sender.request='b'*32;sender._hello_at=float('inf')
            reply=encode_message('challenge',TOKEN if mode!='wrong-key' else 'other-token',session=sender.session,request='c'*32 if mode=='wrong-request' else sender.request,challenge='d'*32)
            sock.recvfrom.side_effect=[(reply,('192.0.2.51',1234 if mode=='wrong-port' else 55355)),BlockingIOError()]
            self.assertEqual(sender.send(ControllerState.released(1,1,'off')),mode=='valid')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux IP_PKTINFO integration')
    def test_linux_receiver_replies_from_the_contacted_address(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'token').write_text(TOKEN)
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1];sock.close()
            process=subprocess.Popen([sys.executable,'-m','powerglove_vision.receiver','--listen','0.0.0.0','--port',str(port),'--token-file',str(root/'token'),'--native-state',str(root/'native'),'--dry-run'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(.05)
            try:
                deadline=time.monotonic()+3
                while True:
                    client.sendto(hello('a'*32),('127.0.0.2',port))
                    try:payload,peer=client.recvfrom(4097);break
                    except socket.timeout:
                        if time.monotonic()>=deadline:self.fail('No receiver reply')
                self.assertEqual(peer,('127.0.0.2',port))
                self.assertEqual(decode_message(payload,TOKEN)['kind'],'challenge')
            finally:
                client.close();process.terminate();process.communicate(timeout=3)
