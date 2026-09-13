# Project: VirtualGlove
# SPDX-License-Identifier: MIT
"""Conservative live gates shared by ready-guide arming and tests."""
from .players import READY_CHECKS, READY_COURSE
from .gesture import SUPPORTED_PROFILES


def game_gate(status, require_link=True):
    age = status.get('worker_status_age_seconds')
    if (type(age) not in (int, float) or not 0 <= age < 3
            or status.get('worker_running') is not True):
        return 'Waiting for fresh tracker status.'
    if status.get('practice_mode') or status.get('tuning', {}).get('active'):
        return 'End all Academy practice and tuning sessions first.'
    if status.get('game_session_active') is not True:
        return 'Launch a registered game on RetroPie.'
    profile = status.get('active_profile', status.get('profile'))
    if profile not in SUPPORTED_PROFILES:
        return 'This game has no supported mapping. Review Games in Setup.'
    core = status.get('emulator')
    if not isinstance(core, str) or not core or core == 'unknown':
        return 'Waiting for the registered game’s emulator identity.'
    expected = 'native' if profile == 'super_glove_ball' and core in {'lr-nestopia-powerglove', 'lr-powerglove-dot'} else 'joystick'
    if status.get('input_mode') != expected:
        return 'The game profile and input mode disagree. Review Games and the emulator selection.'
    if profile == 'program_14':
        if status.get('launch_guard_active') or status.get('controller_context_active') is not True:
            return 'Waiting for the game’s controller context and launch delay.'
        return None
    if status.get('vision_state') != 'active' or status.get('camera_available') is not True:
        return 'Waiting for the camera to become ready.'
    if status.get('calibrated') is not True or status.get('calibrating') or status.get('player', {}).get('needs_center') or status.get('calibration_save_error'):
        return 'Return to the guide’s practice step and center your hand.'
    if status.get('launch_guard_active') or status.get('controller_context_active') is not True:
        return 'Waiting for the game’s controller context and launch delay.'
    if require_link and (status.get('receiver_available') is not True
                         or status.get('controller_enabled') is not True
                         or status.get('worker_controller_enabled') is not True
                         or status.get('controller_request_pending')):
        return 'Waiting for an authenticated receiver link. Check the receiver service and pairing.'
    return None


def essential_complete(player):
    progress = player.get('ready_progress', {})
    return progress.get('course') == READY_COURSE and set(progress.get('completed', [])) == set(READY_CHECKS)
