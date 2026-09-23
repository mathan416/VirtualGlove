# Project: VirtualGlove
# File: src/virtualglove/vision_app.py
# Purpose: Run camera capture, hand tracking, gesture mapping, profile control, diagnostics, and network output.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-10 - Added opt-in process-isolated OpenCV capture.
#   2026-09-09 - Added opt-in process-isolated Direct V4L2 capture.
#   2026-09-09 - Included conditional search activity in bounded native traces.
#   2026-09-09 - Enabled detailed MediaPipe evidence only during finite traces.
#   2026-09-09 - Exposed capture-time tracking loss and recovery timing.
#   2026-09-09 - Removed tuning locks from the inference-to-send boundary.
#   2026-09-08 - Published frame-preparation and palm-reacquisition trace evidence.
#   2026-09-08 - Added a same-descriptor manual-exposure full-pipeline test lane.
#   2026-09-07 - Added optional direct V4L2 capture and portable exposure negotiation.
#   2026-09-07 - Use capture timestamps and throttle derived performance summaries.
#   2026-09-07 - Made MediaPipe plus the bounded curve the default native X/Y path.
#   2026-09-06 - Support measured opt-in Kiyo Pro capture controls and buffer count.
#   2026-09-06 - Add opt-in independent native hand movement tracking.
#   2026-09-06 - Add opt-in correlated latency diagnostics without changing input formats.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-06 - Add complete hand-setup backups and explicit calibration restoration.
#   2026-09-06 - Require fresh centring after player changes before delivery.
#   2026-09-05 - Resumed armed controls from renewable RetroPie game leases.
#   2026-09-05 - Measured fresh-frame publication and controller-transition latency.
#   2026-09-05 - Reported clear proven and experimental tracker names.
#   2026-09-05 - Added latest-frame capture, timing telemetry, and async previews.
#   2026-09-04 - Preloaded vision libraries while keeping idle capture off.
#   2026-09-04 - Logged camera and first-frame startup stage durations.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Added lazy vision activation and a persistent camera-free idle state.
#   2026-09-03 - Added temporary Learn-page vision with automatic state restoration.
#   2026-09-03 - Published startup timing for browser elapsed-time feedback.
#   2026-09-03 - Retain neutral calibration across worker and profile restarts.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.

"""Run camera capture, hand tracking, gesture mapping, profile control, diagnostics, and network output."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import signal
import sys
import time
import threading
import queue
from concurrent.futures import Future
from pathlib import Path

from .tuning import TuningManager
from .camera import CameraUnavailableError, camera_candidates
from .debug_server import SharedDebugState, start_debug_server
from .gesture import (GestureConfig, GestureEngine, joystick_deadzone_bounds,
                      load_calibration, rapid_fire_defaults, save_calibration)
from .matrix import MatrixStatus, UnoQMatrix
from .diagnostic_trace import session_key
from .model import ControllerState
from .profile_control import ActiveGameLease, ProfileCommandServer, ProfileRequest, read_token
from .realtime import (
    DashboardCadence, LatestFrameCapture, LatestPreviewEncoder, LatestStatusPublisher,
    RollingPerformance,
)
from .runtime_assets import ensure_hand_landmarker_model
from .tracker import PALM_ANCHOR, MediaPipeTracker, log_startup_stage
from .transport import UdpSender


PRACTICE_PROFILE = "practice"


def _controller_signature(state: ControllerState) -> tuple:
    """Return gameplay-visible state without sequence, time, or confidence noise."""
    return (
        state.profile,
        state.detected,
        state.calibrated,
        tuple(sorted(state.axes.items())),
        tuple(sorted(state.dpad.items())),
        tuple(sorted(state.buttons.items())),
        tuple(sorted(state.fingers.items())),
        tuple(state.events),
    )


def _dashboard_event_signature(state: ControllerState, *context) -> tuple:
    """Identify UI-visible transitions while ignoring routine native X/Y travel."""
    return (
        state.profile,
        state.detected,
        state.calibrated,
        tuple(sorted(state.dpad.items())),
        tuple(sorted(state.buttons.items())),
        tuple(state.events),
        *context,
    )


def _academy_image_quality(frame, diagnostics: dict, cv2) -> dict:
    """Return advisory hand framing and lighting feedback without retaining pixels."""
    points = diagnostics.get("hand_landmarks") or []
    if len(points) != 21:
        return {"whole_hand_visible": False, "warning": "Show your whole hand clearly."}
    xs = [max(0.0, min(1.0, float(point[0]))) for point in points]
    ys = [max(0.0, min(1.0, float(point[1]))) for point in points]
    margin = min(min(xs), min(ys), 1 - max(xs), 1 - max(ys))
    whole = margin >= .025
    height, width = frame.shape[:2]
    left, right = max(0, int(min(xs) * width)), min(width, int(max(xs) * width) + 1)
    top, bottom = max(0, int(min(ys) * height)), min(height, int(max(ys) * height) + 1)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hand_luma = float(gray[top:bottom, left:right].mean()) if right > left and bottom > top else 0.0
    background_luma = float(gray.mean())
    warning = ""
    if not whole:
        warning = "Move a little farther into the frame so every fingertip is visible."
    elif hand_luma < 55:
        warning = "Your hand looks dark. Add light in front of you if recognition is difficult."
    elif background_luma - hand_luma > 50:
        warning = "The background is much brighter than your hand. Face a light or turn away from the bright window."
    return {"whole_hand_visible": whole, "hand_luma": round(hand_luma, 1),
            "background_luma": round(background_luma, 1), "warning": warning}


def _shutdown_on_signal(_signum: int, _frame: object) -> None:
    """Convert process termination into the vision loop's normal cleanup path."""
    # A container stop can repeat SIGTERM while bounded worker cleanup is still
    # running.  Make termination one-shot so a second signal cannot interrupt
    # resource release and produce a misleading shutdown traceback.
    signal.signal(_signum, signal.SIG_IGN)
    raise KeyboardInterrupt


def _load_config(path: Path | None) -> GestureConfig:
    """Load the current shared recognition thresholds."""
    if path is None:
        candidate = Path(__file__).resolve().parents[2] / "config" / "profiles.json"
        path = candidate if candidate.exists() else None
    if path is None:
        return GestureConfig()
    data = json.loads(path.read_text())
    return GestureConfig(**data.get("recognition", {}))


def build_parser() -> argparse.ArgumentParser:
    """Create the vision worker command-line parser."""
    parser = argparse.ArgumentParser(description="Camera-only VirtualGlove controller")
    parser.add_argument("--receiver", required=True, help="Raspberry Pi hostname or address")
    parser.add_argument("--port", type=int, default=55355)
    tokens = parser.add_mutually_exclusive_group(required=True)
    tokens.add_argument("--token", help="shared receiver token (prefer a private file)")
    tokens.add_argument("--token-file", type=Path, help="private file containing the shared token")
    tokens.add_argument("--device-config", type=Path, help="private device JSON containing the shared token")
    parser.add_argument("--profile", default="off", help="startup profile; may be changed by RetroPie")
    parser.add_argument("--camera", default="auto", help="camera index, or 'auto'")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--fps", type=int, choices=(0, 30, 60), default=0,
        help="camera rate; 0 automatically prefers 30 fps with driver fallback",
    )
    parser.add_argument("--camera-buffers", type=int, choices=(1, 2), default=1,
                        help="V4L2 capture buffers; measured UNO Q candidate uses two")
    parser.add_argument("--kiyo-hdr-off", action="store_true",
                        help="Kiyo Pro only: volatile HDR-off and automatic fixed-rate exposure")
    parser.add_argument(
        "--camera-format", choices=("MJPG", "YUYV"), default="MJPG",
        help="requested V4L2 pixel format for controlled capture benchmarks",
    )
    parser.add_argument(
        "--capture-backend", choices=("opencv", "direct-v4l2"), default="opencv",
        help="camera reader; direct V4L2 falls back safely to OpenCV",
    )
    parser.add_argument(
        "--capture-isolation", choices=("thread", "process"), default="thread",
        help="latest-frame owner; process supports OpenCV and Direct V4L2",
    )
    parser.add_argument(
        "--camera-exposure", choices=("auto", "low-latency", "kiyo-low-latency", "manual"),
        default="auto", help="volatile capability-checked exposure behaviour",
    )
    parser.add_argument("--camera-manual-exposure", type=int, default=None,
                        help="manual V4L2 exposure value; requires Direct V4L2")
    parser.add_argument("--camera-manual-gain", type=int, default=None,
                        help="manual V4L2 gain value; requires Direct V4L2")
    parser.add_argument("--camera-manual-exposure-test", type=int,
                        default=None, help=argparse.SUPPRESS)
    parser.add_argument("--camera-manual-gain-test", type=int,
                        default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--inference-threads", type=int, choices=(1, 2, 4), default=4,
        help="CPU threads for the legacy MediaPipe inference calculators",
    )
    parser.add_argument(
        "--tracking-confidence", type=float, default=.35,
        help="minimum MediaPipe landmark-tracking confidence",
    )
    parser.add_argument(
        "--detection-confidence", type=float, default=.45,
        help="minimum MediaPipe palm-detection confidence",
    )
    parser.add_argument(
        "--tracking-roi-scale", type=float,
        choices=(2.0, 2.25), default=2.25,
        help="next-frame MediaPipe tracking region; 2.25 is the validated default",
    )
    parser.add_argument(
        "--tracker-backend", choices=("legacy", "tasks-video"), default="legacy",
        help=("MediaPipe Hands (legacy) or MediaPipe Tasks Video "
              "(experimental; tasks-video)"),
    )
    parser.add_argument(
        "--tracker-graph", choices=("full", "lean-image"), default="full",
        help="MediaPipe graph output set; lean-image is an output-paused experiment",
    )
    parser.add_argument(
        "--preview-fps", type=float, default=5.0,
        help="maximum diagnostic camera-preview rate",
    )
    parser.add_argument("--glove-color", choices=("none", "white", "black"), default="none")
    parser.add_argument("--no-mirror", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model", type=Path, help="MediaPipe hand-landmarker model")
    parser.add_argument("--web-host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=8088)
    parser.add_argument("--no-matrix", action="store_true", help="disable the UNO Q LED matrix bridge")
    parser.add_argument("--profile-listen", default="0.0.0.0")
    parser.add_argument("--profile-port", type=int, default=55356)
    parser.add_argument("--controller-enabled", action="store_true", help="begin sending controller packets")
    parser.add_argument(
        "--launch-guard-ms", type=int, default=6000,
        help="pause controller packets after a RetroPie game-start request",
    )
    return parser


def _camera_rate_attempts(fps: int) -> tuple[int | None, ...]:
    """Try the preferred/requested rate, then allow the driver to choose."""
    return (30 if fps == 0 else fps, None)


def _v4l2_device_path(camera_device) -> str:
    """Convert OpenCV's numeric device shorthand into its Linux node path."""
    if isinstance(camera_device, int) or str(camera_device).isdigit():
        return f"/dev/video{int(camera_device)}"
    return str(camera_device)


def _open_camera(args: argparse.Namespace):
    """Open and warm the selected UVC camera only when gestures are active."""
    started = time.monotonic()
    import cv2
    log_startup_stage("OpenCV import", started)
    started = time.monotonic()
    candidates = camera_candidates(args.camera)
    log_startup_stage("camera discovery", started)

    test_values = (
        getattr(args, "camera_manual_exposure_test", None),
        getattr(args, "camera_manual_gain_test", None),
    )
    configured_values = (
        getattr(args, "camera_manual_exposure", None),
        getattr(args, "camera_manual_gain", None),
    )
    manual_test = all(value is not None for value in test_values)
    manual_mode = getattr(args, "camera_exposure", "auto") == "manual"
    if any(value is not None for value in test_values) and not manual_test:
        raise ValueError("manual exposure testing requires both exposure and gain")
    if manual_mode and not all(value is not None for value in configured_values):
        raise ValueError("manual exposure requires both exposure and gain")
    if manual_test and any(value is not None for value in configured_values):
        raise ValueError("manual exposure test and saved manual exposure cannot be combined")
    manual_values = test_values if manual_test else configured_values
    manual_enabled = manual_test or manual_mode
    if manual_enabled and getattr(args, "capture_backend", "opencv") != "direct-v4l2":
        raise ValueError("manual exposure requires direct V4L2 capture")
    if manual_enabled and (not sys.platform.startswith("linux")
                           or args.camera_format != "MJPG"
                           or (args.width, args.height) != (640, 480)):
        raise ValueError("manual exposure requires Linux MJPG 640x480")

    for camera_device in candidates:
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        exposure_mode = getattr(args, "camera_exposure", "auto")
        if getattr(args, "kiyo_hdr_off", False):
            exposure_mode = "kiyo-low-latency"
        if manual_enabled:
            # Manual exposure owns all changes through Direct V4L2's
            # streaming descriptor. Do not open a second control descriptor.
            exposure_mode = "manual-test" if manual_test else "manual"
        exposure_report = {"requested": exposure_mode, "supported": False, "applied": False}
        camera_control_error = None
        if exposure_mode in ("low-latency", "kiyo-low-latency"):
            from .camera_controls import configure_low_latency
            try:
                exposure_report = configure_low_latency(_v4l2_device_path(camera_device))
            except (OSError, ValueError, RuntimeError) as exc:
                camera_control_error = str(exc)
                exposure_report["reason"] = camera_control_error
                print(f"Camera controls unavailable: {exc}", file=sys.stderr, flush=True)
        kiyo_applied = False
        if exposure_mode == "kiyo-low-latency":
            from .kiyo_camera import configure_kiyo
            try:
                kiyo_applied = configure_kiyo(camera_device)
            except (OSError, ValueError, RuntimeError) as exc:
                camera_control_error = str(exc)
                print(f"Camera controls unavailable: {exc}", file=sys.stderr, flush=True)
        # Automatic mode prefers the measured 30 fps path. If that prevents a
        # camera from producing frames, reopen it without forcing a rate and
        # accept the driver's native choice.
        rate_attempts = _camera_rate_attempts(args.fps)
        for requested_rate in rate_attempts:
            process_opencv_error = None
            process_opencv = (
                getattr(args, "capture_backend", "opencv") == "opencv"
                and getattr(args, "capture_isolation", "thread") == "process"
                and sys.platform.startswith("linux")
                and args.camera_format == "MJPG"
                and args.width == 640 and args.height == 480
            )
            if process_opencv:
                metadata = {
                    "camera_fps_requested": "auto" if args.fps == 0 else args.fps,
                    "camera_hdr_off_requested": exposure_mode == "kiyo-low-latency",
                    "camera_hdr_off_command_sent": kiyo_applied,
                    "camera_exposure_mode": exposure_mode,
                    "camera_exposure_supported": exposure_report.get("supported", False),
                    "camera_exposure_applied": bool(
                        exposure_report.get("applied") or kiyo_applied
                    ),
                    "camera_exposure_fixed_rate": exposure_report.get(
                        "fixed_frame_rate", False
                    ),
                    "camera_control_error": camera_control_error,
                }
                try:
                    import numpy as np
                    from .process_capture import ProcessOpenCVCapture
                    isolated = ProcessOpenCVCapture(
                        camera_device, backend, args.camera_format, args.width,
                        args.height, requested_rate,
                        getattr(args, "camera_buffers", 1), np, metadata=metadata,
                    )
                    return cv2, isolated
                except Exception as exc:
                    process_opencv_error = str(exc)
            started = time.monotonic()
            candidate = cv2.VideoCapture(camera_device, backend)
            log_startup_stage("camera open", started)
            started = time.monotonic()
            candidate.set(
                cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.camera_format)
            )
            candidate.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            rate_accepted = (
                candidate.set(cv2.CAP_PROP_FPS, requested_rate)
                if requested_rate is not None else None
            )
            requested_buffers = getattr(args, "camera_buffers", 1)
            buffers_accepted = candidate.set(cv2.CAP_PROP_BUFFERSIZE, requested_buffers)
            log_startup_stage("camera settings", started)
            process_direct = (
                getattr(args, "capture_backend", "opencv") == "direct-v4l2"
                and getattr(args, "capture_isolation", "thread") == "process"
                and sys.platform.startswith("linux")
                and args.camera_format == "MJPG"
                and args.width == 640 and args.height == 480
            )
            if process_direct:
                # OpenCV negotiates the requested camera format and rate, but it
                # must not dequeue or decode a frame in process-isolated mode.
                # Release its descriptor before the child becomes the sole
                # streaming owner. Some UVC cameras can block for seconds on the
                # otherwise redundant parent-side warm-up read.
                fourcc = int(candidate.get(cv2.CAP_PROP_FOURCC))
                negotiated_format = "".join(
                    chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)
                ).rstrip("\x00")
                metadata = {
                    "camera_format": negotiated_format or args.camera_format,
                    "camera_width": round(candidate.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "camera_height": round(candidate.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "camera_fps_requested": "auto" if args.fps == 0 else args.fps,
                    "camera_fps_preferred": requested_rate,
                    "camera_fps_request_accepted": rate_accepted,
                    "camera_fps": round(candidate.get(cv2.CAP_PROP_FPS), 1),
                    "camera_buffers_requested": requested_buffers,
                    "camera_buffers": candidate.get(cv2.CAP_PROP_BUFFERSIZE),
                    "camera_buffers_accepted": buffers_accepted,
                    "camera_hdr_off_requested": exposure_mode == "kiyo-low-latency",
                    "camera_hdr_off_command_sent": kiyo_applied,
                    "camera_exposure_mode": exposure_mode,
                    "camera_exposure_supported": exposure_report.get("supported", False),
                    "camera_exposure_applied": bool(
                        exposure_report.get("applied") or kiyo_applied
                    ),
                    "camera_exposure_fixed_rate": exposure_report.get(
                        "fixed_frame_rate", False
                    ),
                    "camera_control_error": camera_control_error,
                    "capture_isolation_requested": "process",
                    "capture_isolation": "process",
                    "capture_isolation_fallback": None,
                }
                candidate.release()
                try:
                    import numpy as np
                    from .process_capture import ProcessDirectV4L2Capture
                    isolated = ProcessDirectV4L2Capture(
                        _v4l2_device_path(camera_device), requested_buffers, np,
                        metadata=metadata,
                        manual_exposure=(
                            manual_values[0] if manual_enabled else None
                        ),
                        manual_gain=manual_values[1] if manual_enabled else None,
                    )
                    isolated.metadata.update({
                        "capture_backend_requested": "direct-v4l2",
                        "capture_backend": "direct-v4l2",
                        "capture_backend_fallback": None,
                        "camera_exposure_mode": (
                            "manual-test" if manual_test else exposure_mode
                        ),
                    })
                    if manual_enabled:
                        isolated.metadata.update({
                            "camera_manual_exposure_requested": manual_values[0],
                            "camera_manual_gain_requested": manual_values[1],
                            "camera_manual_exposure": manual_values[0],
                            "camera_manual_gain": manual_values[1],
                        })
                    return cv2, isolated
                except Exception as exc:
                    if manual_test:
                        raise RuntimeError(
                            f"manual exposure test could not start safely: {exc}"
                        ) from exc
                    metadata.update({
                        "capture_backend": "opencv",
                        "capture_backend_fallback": str(exc),
                        "capture_isolation": "thread",
                        "capture_isolation_fallback": str(exc),
                        "camera_exposure_fallback": manual_mode,
                    })
                    candidate = cv2.VideoCapture(camera_device, backend)
                    candidate.set(
                        cv2.CAP_PROP_FOURCC,
                        cv2.VideoWriter_fourcc(*args.camera_format),
                    )
                    candidate.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                    candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
                    if requested_rate is not None:
                        candidate.set(cv2.CAP_PROP_FPS, requested_rate)
                    candidate.set(cv2.CAP_PROP_BUFFERSIZE, requested_buffers)
                    ok, fallback_frame = candidate.read()
                    if not ok:
                        candidate.release()
                        continue
                    return cv2, LatestFrameCapture(
                        candidate, fallback_frame, metadata=metadata,
                    )
            started = time.monotonic()
            warmup_deadline = time.monotonic() + 5.0
            while candidate.isOpened() and time.monotonic() < warmup_deadline:
                ok, _frame = candidate.read()
                if ok:
                    log_startup_stage("first camera frame", started)
                    fourcc = int(candidate.get(cv2.CAP_PROP_FOURCC))
                    negotiated_format = "".join(
                        chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)
                    ).rstrip("\x00")
                    metadata = {
                        "camera_format": negotiated_format or args.camera_format,
                        "camera_width": round(candidate.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        "camera_height": round(candidate.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        "camera_fps_requested": "auto" if args.fps == 0 else args.fps,
                        "camera_fps_preferred": requested_rate,
                        "camera_fps_request_accepted": rate_accepted,
                        "camera_fps": round(candidate.get(cv2.CAP_PROP_FPS), 1),
                        "camera_buffers_requested": requested_buffers,
                        "camera_buffers": candidate.get(cv2.CAP_PROP_BUFFERSIZE),
                        "camera_buffers_accepted": buffers_accepted,
                        "camera_hdr_off_requested": exposure_mode == "kiyo-low-latency",
                        "camera_hdr_off_command_sent": kiyo_applied,
                        "camera_exposure_mode": exposure_mode,
                        "camera_exposure_supported": exposure_report.get("supported", False),
                        "camera_exposure_applied": bool(exposure_report.get("applied") or kiyo_applied),
                        "camera_exposure_fixed_rate": exposure_report.get("fixed_frame_rate", False),
                        "camera_control_error": camera_control_error,
                        "capture_isolation_requested": getattr(
                            args, "capture_isolation", "thread"
                        ),
                        "capture_isolation": "thread",
                        "capture_isolation_fallback": process_opencv_error,
                    }
                    if (getattr(args, "capture_backend", "opencv") == "direct-v4l2"
                            and sys.platform.startswith("linux")
                            and args.camera_format == "MJPG"
                            and args.width == 640 and args.height == 480):
                        candidate.release()
                        direct = None
                        try:
                            import numpy as np
                            from .v4l2_capture import DirectV4L2Capture
                            direct = DirectV4L2Capture(
                                _v4l2_device_path(camera_device), requested_buffers, cv2, np,
                            )
                            direct_frame, direct_at = _first_direct_frame(direct)
                            if manual_enabled:
                                from .camera_controls import (
                                    configure_manual_on_fd, restore_automatic_on_fd,
                                )
                                manual_report = configure_manual_on_fd(
                                    direct.fd, manual_values[0], manual_values[1],
                                )
                                if not manual_report.get("applied"):
                                    untouched = not manual_report.get("supported")
                                    restored = restore_automatic_on_fd(direct.fd)
                                    manual_report["automatic_fallback"] = untouched or restored
                                    if not (untouched or restored):
                                        raise RuntimeError(
                                            "camera rejected manual settings and automatic exposure could not be restored"
                                        )
                                    if manual_test:
                                        raise RuntimeError(manual_report.get(
                                            "reason", "manual exposure test was not applied"
                                        ))
                                else:
                                    direct.before_close = restore_automatic_on_fd
                                exposure_report = manual_report
                            metadata.update({
                                "capture_backend_requested": "direct-v4l2",
                                "capture_backend": "direct-v4l2",
                                "capture_backend_fallback": None,
                                **direct.last_metadata,
                            })
                            if manual_enabled:
                                manual_applied = bool(exposure_report.get("applied"))
                                metadata.update({
                                    "camera_exposure_mode": "manual-test" if manual_test else "manual",
                                    "camera_exposure_supported": bool(exposure_report.get("supported")),
                                    "camera_exposure_applied": manual_applied,
                                    "camera_exposure_fallback": bool(
                                        exposure_report.get("automatic_fallback")
                                    ),
                                    "camera_manual_exposure_requested": manual_values[0],
                                    "camera_manual_gain_requested": manual_values[1],
                                    "camera_manual_exposure": manual_values[0] if manual_applied else None,
                                    "camera_manual_gain": manual_values[1] if manual_applied else None,
                                    "camera_manual_limits": exposure_report.get("limits", {}),
                                    "camera_control_error": exposure_report.get("reason"),
                                })
                            return cv2, LatestFrameCapture(
                                direct, direct_frame, first_captured_at=direct_at,
                                metadata=metadata,
                            )
                        except Exception as exc:
                            if direct is not None:
                                direct.close()
                            if manual_test:
                                raise RuntimeError(
                                    f"manual exposure test could not start safely: {exc}"
                                ) from exc
                            metadata.update({
                                "capture_backend_requested": "direct-v4l2",
                                "capture_backend": "opencv",
                                "capture_backend_fallback": str(exc),
                                "capture_isolation_requested": getattr(
                                    args, "capture_isolation", "thread"
                                ),
                                "capture_isolation": "thread",
                                "capture_isolation_fallback": str(exc),
                                "camera_exposure_fallback": manual_mode,
                            })
                            candidate = cv2.VideoCapture(camera_device, backend)
                            candidate.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.camera_format))
                            candidate.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                            candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
                            if requested_rate is not None:
                                candidate.set(cv2.CAP_PROP_FPS, requested_rate)
                            candidate.set(cv2.CAP_PROP_BUFFERSIZE, requested_buffers)
                            ok, fallback_frame = candidate.read()
                            if not ok:
                                candidate.release()
                                continue
                            return cv2, LatestFrameCapture(
                                candidate, fallback_frame, metadata=metadata,
                            )
                    metadata.update({
                        "capture_backend_requested": getattr(args, "capture_backend", "opencv"),
                        "capture_backend": "opencv",
                        "capture_backend_fallback": None,
                    })
                    return cv2, LatestFrameCapture(candidate, _frame, metadata=metadata)
                time.sleep(0.1)
            candidate.release()
    raise CameraUnavailableError(f"camera '{args.camera}' is unavailable; waiting for a USB camera")


def _first_direct_frame(source, timeout: float = 5.0):
    """Wait through transient V4L2 startup failures for one valid frame."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            ok, frame, captured_at = source.read_with_timestamp()
        except Exception as exc:
            last_error = exc
            time.sleep(0.005)
            continue
        if ok:
            return frame, captured_at
        time.sleep(0.005)
    if last_error is not None:
        raise RuntimeError(
            f"direct V4L2 produced no valid first frame: {last_error}"
        ) from last_error
    raise RuntimeError("direct V4L2 produced no valid first frame")


def _close_vision(capture, tracker) -> None:
    """Release optional camera and MediaPipe resources after a profile transition."""
    if capture is not None:
        capture.release()
    if tracker is not None:
        tracker.close()


_VISION_JOBS = queue.Queue(maxsize=1)
_VISION_IO_THREAD = None


def _background_call(function, *args):
    """Run serialized camera I/O on one daemon thread, leaving control responsive."""
    global _VISION_IO_THREAD
    future = Future()

    def run():
        """Complete jobs serially; a blocked driver cannot spawn additional workers."""
        while True:
            result, operation, arguments = _VISION_JOBS.get()
            try:
                result.set_result(operation(*arguments))
            except Exception as exc:
                result.set_exception(exc)

    if _VISION_IO_THREAD is None:
        _VISION_IO_THREAD = threading.Thread(target=run, name="vision-io", daemon=True)
        _VISION_IO_THREAD.start()
    _VISION_JOBS.put_nowait((future, function, args))
    return future


def _preload_vision_libraries() -> None:
    """Warm library imports without opening the camera or constructing a tracker."""
    try:
        for module in ("cv2", "mediapipe"):
            started = time.monotonic()
            importlib.import_module(module)
            log_startup_stage(f"preload {module}", started)
    except Exception as exc:
        # Activation retries normally and reports an actionable error if needed.
        print(f"Vision preload unavailable; will retry on activation: {exc}",
              file=sys.stderr, flush=True)


def _prepare_vision(args):
    """Resolve the model and log camera/tracker startup stages in one I/O job."""
    preparation_started = time.monotonic()
    print("Vision startup: preparation started", file=sys.stderr, flush=True)
    capture = tracker = None
    try:
        model_path = None
        if args.tracker_backend == "tasks-video":
            model_path = args.model
            if model_path is None or model_path.name == "hand_landmarker.task":
                data_directory = model_path.parent.parent if model_path is not None else Path("data")
                model_path = ensure_hand_landmarker_model(data_directory)
            elif not model_path.is_file():
                raise RuntimeError(f"MediaPipe hand model not found: {model_path}")
        log_startup_stage("tracker asset selection", preparation_started)
        cv2, capture = _open_camera(args)
        tracker = MediaPipeTracker(
            args.glove_color,
            mirror=not args.no_mirror,
            model_path=model_path,
            inference_threads=args.inference_threads,
            tracking_confidence=args.tracking_confidence,
            detection_confidence=args.detection_confidence,
            tracking_roi_scale=args.tracking_roi_scale,
            backend=args.tracker_backend,
            graph_mode=args.tracker_graph,
            directional_search=True,
            tracking_evidence=getattr(args, "tracking_evidence", False),
        )
        log_startup_stage("preparation total", preparation_started)
        return cv2, capture, tracker
    except Exception:
        _close_vision(capture, tracker)
        raise


def _effective_profile(profile: str | None, practice_mode: bool) -> str | None:
    """Choose a tracking profile while preserving an intentionally selected off state."""
    return PRACTICE_PROFILE if practice_mode else (
        None if profile == "program_14" else profile
    )


def _native_xy_active(engine: GestureEngine, practice_mode: bool,
                      tuning_active: bool, needs_center: bool,
                      emulator: str = "") -> bool:
    """Use native coordinates only in ready Super Glove Ball gameplay."""
    return (
        engine.profile == "super_glove_ball"
        and emulator in {"lr-nestopia-powerglove", "lr-powerglove-dot"}
        and engine.calibrated
        and not practice_mode
        and not tuning_active
        and not needs_center
    )


def _native_xy_source(active: bool) -> str:
    """Name the coordinate authority independently of response mode."""
    if not active:
        return "inactive"
    return "mediapipe"


def _joystick_grid_status(engine, practice_mode: bool, needs_center: bool = False):
    """Expose read-only bounds in the same normalized coordinates as the preview."""
    if not practice_mode or needs_center or engine is None or not engine.calibrated:
        return None
    reference = engine.calibration
    if reference is None:
        return None
    values = (reference.palm_x, reference.palm_y, reference.palm_scale,
              reference.noise_x, reference.noise_y, reference.roll)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
            or not 0 <= reference.palm_x <= 1 or not 0 <= reference.palm_y <= 1
            or not 0 < reference.palm_scale <= 2
            or not 0 <= reference.noise_x <= 1 or not 0 <= reference.noise_y <= 1
            or not -math.pi <= reference.roll <= math.pi
            or not reference.valid_reach()):
        return None
    bounds = joystick_deadzone_bounds(engine.config, reference)
    size = bounds["half_size"] * 2
    minimum_size = min(1.0, 1.5 * reference.palm_scale)
    if not all(math.isfinite(value) for value in (*bounds.values(), minimum_size)):
        return None
    return {
        "anchor": {"x": reference.palm_x, "y": reference.palm_y},
        "center": {"x": bounds["center_x"], "y": bounds["center_y"]},
        "half_size": size / 2,
        "minimum_size": minimum_size,
    }


def _input_mode(profile: str | None, emulator: str) -> str:
    """Select native input only for a supported native core/profile pair."""
    return (
        "native" if profile == "super_glove_ball"
        and emulator in {"lr-nestopia-powerglove", "lr-powerglove-dot"} else "joystick"
    )


def _update_controller_state(
    engine: GestureEngine, result, native_xy_active: bool,
):
    """Publish the latest valid MediaPipe coordinate for native X/Y."""
    if not native_xy_active:
        return engine.update(result.observation), _native_xy_source(False)
    # The ordinary gesture path updates discrete actions; the native path
    # also uses this same frame's newest palm coordinate. Bounded smoothing
    # remains an engineering comparison, not the production native route.
    return (
        engine.update_native_motion(
            result.observation, result.observation,
            bounded=False,
        ),
        _native_xy_source(True),
    )


def _native_trace_fields(engine: GestureEngine, result, active: bool) -> dict:
    """Expose finite, non-biometric evidence for native reacquisition analysis."""
    observation = result.observation
    observed_xy = None
    if observation.detected and all(
        math.isfinite(value) for value in (observation.palm_x, observation.palm_y)
    ):
        observed_xy = [observation.palm_x, observation.palm_y]
    return {
        "observation_detected": bool(observation.detected),
        "observed_xy": observed_xy,
        "native_xy_active": bool(active),
        "latest_recovery_pending": bool(engine._latest_recovery_pending),
        "latest_confirmation_pending": bool(engine._latest_confirmation_pending),
        "tracking_path": result.diagnostics.get("tracking_path"),
        "tracking_observation_cause": result.diagnostics.get(
            "tracking_observation_cause"
        ),
        "loss_start_cause": result.diagnostics.get("loss_start_cause"),
        "last_recovery_loss_start_cause": result.diagnostics.get(
            "last_recovery_loss_start_cause"
        ),
        "palm_detector_invoked": result.diagnostics.get("palm_detector_invoked"),
        "palm_detection_count": result.diagnostics.get("palm_detection_count"),
        "hand_presence_score": result.diagnostics.get("hand_presence_score"),
        "palm_reacquired": bool(result.diagnostics.get("palm_reacquired", False)),
        "hand_missing_streak": result.diagnostics.get("hand_missing_streak", 0),
        "tracking_recovered": bool(result.diagnostics.get("tracking_recovered", False)),
        "recovery_gap_ms": result.diagnostics.get("recovery_gap_ms"),
        "recovery_missing_span_ms": result.diagnostics.get("recovery_missing_span_ms"),
        "recovery_inference_ms": (
            result.diagnostics.get("tracking_inference_ms")
            if result.diagnostics.get("tracking_recovered") else None
        ),
        "frame_preparation": result.diagnostics.get("frame_preparation"),
        "directional_search_active": bool(
            result.diagnostics.get("directional_search_active", False)
        ),
        "directional_search_offset": result.diagnostics.get(
            "directional_search_offset", (0.0, 0.0)
        ),
        "directional_search_phase": result.diagnostics.get(
            "directional_search_phase", "inactive"
        ),
    }


TRACKING_STATUS_FIELDS = (
    "frame_preparation",
    "tracking_path",
    "tracking_observation_cause",
    "loss_start_cause",
    "current_missing_causes",
    "last_recovery_loss_start_cause",
    "last_recovery_missing_causes",
    "missing_cause_totals",
    "palm_detector_invoked",
    "palm_detection_count",
    "hand_presence_score",
    "palm_reacquired",
    "hand_missing_streak",
    "landmark_continuations_total",
    "palm_detection_packets_total",
    "palm_redetections_total",
    "palm_reacquisitions_total",
    "hand_missing_results_total",
    "invalid_landmark_results_total",
    "tracking_recovered",
    "tracking_inference_ms",
    "current_tracking_loss_ms",
    "recovery_gap_ms",
    "recovery_missing_span_ms",
    "last_recovery_gap_ms",
    "last_recovery_missing_span_ms",
    "last_recovery_inference_ms",
    "longest_tracking_loss_ms",
    "directional_search_active",
    "directional_search_offset",
)


def _launch_guard_active(deadline: float, now: float | None = None) -> bool:
    """Return whether RetroPie's pre-emulator input guard is still active."""
    return (time.monotonic() if now is None else now) < deadline


def _consume_game_lease(
    request: ProfileRequest | None, lease: ActiveGameLease, now: float,
) -> tuple[ProfileRequest | None, bool]:
    """Reduce a profile signal to a real transition and an optional lease expiry."""
    if request is not None and request.session_id is not None:
        if not lease.refresh(request, now):
            request = None
    elif request is not None:
        lease.clear()
    return request, lease.expire(now)


def _controller_context_active(lease: ActiveGameLease, profile_source: str) -> bool:
    """Allow output only for a live registered game or an intentional manual context."""
    return lease.session_id is not None or profile_source in {
        "Dashboard", "RetroPie launch hook",
    }


def _requested_rapid_fire(request, dashboard_request, lease_expired, current):
    """Preserve a game's switches across practice and clear them on manual/off changes."""
    if lease_expired or dashboard_request is not None:
        return None, None
    if request is not None:
        return request.rapid_a, request.rapid_b
    return current


def _base_status(
    profile: str | None,
    game: str,
    source: str,
    controller_enabled: bool,
    *,
    practice_mode: bool = False,
    emulator: str = "",
    rapid_a: bool | None = None,
    rapid_b: bool | None = None,
) -> dict:
    """Build a neutral dashboard state for idle, starting, and error modes."""
    vision_profile = _effective_profile(profile, practice_mode)
    status = ControllerState.released(
        0, time.monotonic(), vision_profile or "off"
    ).to_status_dict()
    status.update({
        "calibrating": False,
        "game": game,
        "active_profile": profile or "off",
        "vision_profile": vision_profile or "off",
        "practice_mode": practice_mode,
        "profile_source": source,
        "receiver_available": False,
        "receiver_error": (
            "Practice mode; controller transmission is paused"
            if practice_mode
            else ("Gestures are paused" if profile in (None, "program_14")
                  else "Vision is not ready")
        ),
        "controller_enabled": controller_enabled,
        "camera_available": False,
        "native_xy_source": "inactive",
        "emulator": emulator,
        "input_mode": _input_mode(profile, emulator),
    })
    default_a, default_b = rapid_fire_defaults(profile or "off")
    if profile == "program_14":
        rapid_a = rapid_b = False
    status["rapid_fire"] = {
        "a": default_a if rapid_a is None else rapid_a,
        "b": default_b if rapid_b is None else rapid_b,
        "default_a": default_a,
        "default_b": default_b,
        "override_a": rapid_a,
        "override_b": rapid_b,
    }
    return status


def load_worker_token(args: argparse.Namespace) -> str:
    """Read the pairing secret without putting it in the supervised process arguments."""
    configured = json.loads(args.device_config.read_text()).get("token") if args.device_config else args.token
    if configured is not None and not isinstance(configured, str):
        raise ValueError("device token must be text")
    return read_token(configured, args.token_file)


def main() -> int:
    """Keep profile control online while starting vision resources only when needed."""
    args = build_parser().parse_args()
    calibration_path = Path(__file__).resolve().parents[2] / "data" / "calibration.json"
    retained_calibration = load_calibration(calibration_path)
    calibration_save_error = None
    matrix = UnoQMatrix(enabled=not args.no_matrix)
    current_profile: str | None = None if args.profile == "off" else args.profile
    current_rapid_a: bool | None = None
    current_rapid_b: bool | None = None
    current_game = "Startup default"
    profile_source = "startup"
    current_emulator = ""
    controller_enabled = args.controller_enabled
    practice_mode = False
    token = load_worker_token(args)
    sender = UdpSender(args.receiver, args.port, token)
    trace = getattr(sender, "trace", None)
    # Extra MediaPipe evidence exists only for an explicitly enabled finite
    # diagnostic trace; the normal gameplay graph remains unchanged.
    args.tracking_evidence = trace is not None
    profile_server = ProfileCommandServer(args.profile_listen, args.profile_port, token)
    shared = SharedDebugState()
    shared.tuning = TuningManager(calibration_path.with_name("gesture-tuning.json"))
    preview_encoder = LatestPreviewEncoder(shared.update_frame)
    status_publisher = LatestStatusPublisher(shared.update_status)
    performance = RollingPerformance()
    performance_snapshot = {}
    performance_snapshot_at = 0.0
    detailed_status = {}
    detailed_status_at = 0.0
    last_detail_signature = None
    server = start_debug_server(shared, args.web_host, args.web_port)
    capture = tracker = engine = cv2 = None
    vision_job = _background_call(_preload_vision_libraries)
    vision_operation = "preload"
    vision_started_at = time.time()
    startup_timer = None
    retry_at = 0.0
    read_failures = 0
    capture_failure_since = None
    last_capture_sequence = 0
    last_capture_at = None
    capture_skipped_total = 0
    last_inference_started = None
    last_controller_signature = None
    dashboard_cadence = DashboardCadence(10.0)
    preview_at = 0.0
    vision_error: str | None = None
    launch_guard_until = 0.0
    active_game_lease = ActiveGameLease()
    last_launch_session = None
    live_rapid_session = None
    live_rapid_values = (None, None)

    matrix.set_profile(current_profile)
    matrix.set_status(
        MatrixStatus.READY if current_profile == "program_14"
        else MatrixStatus.GESTURES_IDLE if current_profile is None
        else MatrixStatus.LOADING
    )
    signal.signal(signal.SIGTERM, _shutdown_on_signal)

    try:
        while True:
            old_vision_profile = _effective_profile(current_profile, practice_mode)
            old_rapid_fire = (current_rapid_a, current_rapid_b)
            request, lease_expired = _consume_game_lease(
                profile_server.take(), active_game_lease, time.monotonic()
            )
            if live_rapid_session != active_game_lease.session_id:
                live_rapid_session = None
                live_rapid_values = (None, None)
            # Give the authenticated game lifecycle command priority without
            # consuming a simultaneous Dashboard request; it remains queued
            # for the following loop iteration.
            dashboard_request = None if request is not None or lease_expired else shared.take_profile_request()
            if dashboard_request is not None:
                live_rapid_session = None
                live_rapid_values = (None, None)
            requested_profile = None if lease_expired else request.profile if request is not None else (
                dashboard_request[0] if dashboard_request is not None else current_profile
            )
            requested_emulator = (
                "" if lease_expired or dashboard_request is not None
                else request.emulator if request is not None else current_emulator
            )
            requested_rapid_a, requested_rapid_b = _requested_rapid_fire(
                request, dashboard_request, lease_expired,
                (current_rapid_a, current_rapid_b),
            )
            if live_rapid_session is not None:
                requested_rapid_a, requested_rapid_b = live_rapid_values
            profile_requested = request is not None or dashboard_request is not None or lease_expired
            practice_request = shared.take_practice_request()
            if request is not None and request.session_id and request.profile is not None:
                if request.session_id != last_launch_session:
                    last_launch_session = request.session_id
                    shared.game_controller_transition(
                        last_launch_session, True,
                        not (practice_mode if practice_request is None else practice_request)
                        and not shared.tuning.active(),
                    )
            elif lease_expired or (request is not None and request.profile is None):
                shared.game_controller_transition(last_launch_session, False)
            transition_requested = profile_requested or practice_request is not None
            if transition_requested:
                last_controller_signature = None
                if controller_enabled and engine is not None:
                    # End the old profile with a release in its own sequence
                    # space. The next session may restart numbering without a
                    # stale held button crossing the game/profile boundary.
                    sender.send(ControllerState.released(
                        2_147_483_647, time.monotonic(), engine.profile, engine.calibrated
                    ))
                # A terminal release must never share a session with later frames.
                sender.new_session()
                current_profile = requested_profile
                current_emulator = requested_emulator
                current_rapid_a = requested_rapid_a
                current_rapid_b = requested_rapid_b
                if current_profile == "program_14":
                    current_rapid_a = current_rapid_b = False
                if profile_requested:
                    if request is not None:
                        current_game = request.rom or request.system or "No game"
                        profile_source = "RetroPie launch hook"
                        # runcommand-onstart fires before RetroArch owns the
                        # display. Keep newly started or already-enabled output
                        # from driving the launch/configuration menu.
                        if request.profile is not None:
                            # A leased request is not sent until RetroArch is
                            # actually running, so it needs only a short input
                            # initialization guard. Legacy one-shot hooks keep
                            # the full pre-emulator guard.
                            guard_ms = 1000 if request.session_id else max(
                                0, int(getattr(args, "launch_guard_ms", 6000))
                            )
                            launch_guard_until = time.monotonic() + guard_ms / 1000.0
                    elif lease_expired:
                        current_game = "No game"
                        profile_source = "RetroPie game session expired"
                    else:
                        assert dashboard_request is not None
                        profile_source = dashboard_request[1]
                        current_game = dashboard_request[2]
                if practice_request is not None:
                    practice_mode = practice_request

                vision_profile = _effective_profile(current_profile, practice_mode)
                if (vision_profile != old_vision_profile
                        or (current_rapid_a, current_rapid_b) != old_rapid_fire):
                    # Reuse camera/tracker between active profiles; I/O cleanup is asynchronous.
                    engine = None
                    status_publisher.submit(
                        _base_status(
                            current_profile, current_game, profile_source,
                            controller_enabled, practice_mode=practice_mode,
                            emulator=current_emulator,
                            rapid_a=current_rapid_a, rapid_b=current_rapid_b,
                        ),
                        clear_frame=True,
                    )
                    retry_at = 0.0
                    read_failures = 0
                    capture_failure_since = None
                    vision_error = None
                matrix.set_profile(None if practice_mode else current_profile)
                if practice_mode:
                    matrix.set_status(MatrixStatus.TUNING if shared.tuning.active() else MatrixStatus.LEARNING)
                elif vision_profile is None:
                    matrix.set_status(
                        MatrixStatus.READY if current_profile == "program_14"
                        else MatrixStatus.GESTURES_IDLE
                    )
                elif vision_profile != old_vision_profile:
                    matrix.set_status(MatrixStatus.LOADING)
                elif engine is not None:
                    matrix.set_status(MatrixStatus.READY)

            take_rapid_request = getattr(shared, "take_rapid_fire_request", None)
            rapid_request = take_rapid_request() if callable(take_rapid_request) else None
            if isinstance(rapid_request, tuple) and len(rapid_request) == 4:
                rapid_request_id, expected_game, rapid_a, rapid_b = rapid_request
                lease_game = Path(active_game_lease.rom).name
                # A Dashboard edit is live only for the authenticated running
                # game it named. It cannot silently carry into the next ROM.
                if (active_game_lease.session_id is None
                        or lease_game.casefold() != Path(expected_game).name.casefold()):
                    shared.finish_rapid_fire(
                        rapid_request_id,
                        "The registered game changed before the setting could be applied."
                    )
                elif current_profile == "program_14" or practice_mode or shared.tuning.active():
                    shared.finish_rapid_fire(
                        rapid_request_id,
                        "Program 14 has no gesture rapid fire."
                        if current_profile == "program_14"
                        else "Finish Academy, camera tests, or gesture tuning before applying."
                    )
                else:
                    live_rapid_session = active_game_lease.session_id
                    live_rapid_values = (rapid_a, rapid_b)
                    current_rapid_a, current_rapid_b = live_rapid_values
                    if engine is not None:
                        default_a, default_b = rapid_fire_defaults(engine.profile)
                        engine.rapid_a = default_a if rapid_a is None else rapid_a
                        engine.rapid_b = default_b if rapid_b is None else rapid_b
                    shared.finish_rapid_fire(rapid_request_id)

            try:
                restored_calibration = shared.tuning.apply_calibration_restore()
                if restored_calibration is not None:
                    shared.request_controller(False)
                    retained_calibration = restored_calibration
                    if engine is not None:
                        engine = GestureEngine(
                            engine.profile, config=engine.config,
                            calibration=restored_calibration,
                            rapid_a=engine.rapid_a, rapid_b=engine.rapid_b,
                        )
                    last_controller_signature = None
                    calibration_save_error = None
            except OSError as exc:
                calibration_save_error = "Hand-setup restore is paused: " + str(exc)

            controller_request = shared.take_controller_request()
            if shared.tuning.active():
                controller_request = False
            if controller_request is not None and controller_request != controller_enabled:
                if not controller_request and engine is not None and not practice_mode:
                    sender.send(ControllerState.released(
                        2_147_483_647, time.monotonic(), current_profile or "off", engine.calibrated
                    ))
                sender.new_session()
                controller_enabled = controller_request
                if controller_enabled and active_game_lease.session_id is None \
                        and profile_source == "startup":
                    profile_source = "Dashboard"
                    current_game = "Manual selection"

            if shared.take_calibration_request() and engine is not None:
                shared.tuning.begin_center()
                engine.begin_calibration()
                last_controller_signature = None

            vision_profile = _effective_profile(current_profile, practice_mode)
            if vision_job is not None and vision_job.done():
                try:
                    result = vision_job.result()
                    if vision_operation == "open":
                        cv2, capture, tracker = result
                        last_capture_sequence = 0
                        last_capture_at = None
                        capture_failure_since = None
                        vision_error = None
                except Exception as exc:
                    vision_error = str(exc)
                    retry_at = time.monotonic() + 5.0
                    print(f"VirtualGlove: {exc}", file=sys.stderr, flush=True)
                finally:
                    vision_job = None
                    vision_operation = None

            if vision_profile is None:
                # Do not wait for an in-flight camera open/read/close to apply off.
                if capture is not None and vision_job is None:
                    vision_job = _background_call(_close_vision, capture, tracker)
                    vision_operation = "close"
                    capture = tracker = engine = cv2 = None
                status = _base_status(
                    current_profile, current_game, profile_source, controller_enabled,
                    emulator=current_emulator,
                    rapid_a=current_rapid_a, rapid_b=current_rapid_b,
                )
                status.update(active_game_lease.snapshot(time.monotonic()))
                status["controller_context_active"] = _controller_context_active(
                    active_game_lease, profile_source
                )
                status["vision_state"] = "idle"
                status_publisher.submit(status, clear_frame=True)
                matrix.set_status(
                    MatrixStatus.READY if current_profile == "program_14"
                    else MatrixStatus.GESTURES_IDLE
                )
                time.sleep(0.1)
                continue

            if capture is None or tracker is None or cv2 is None:
                status = _base_status(current_profile, current_game, profile_source,
                                      controller_enabled, practice_mode=practice_mode,
                                      emulator=current_emulator,
                                      rapid_a=current_rapid_a,
                                      rapid_b=current_rapid_b)
                status.update(active_game_lease.snapshot(time.monotonic()))
                status["controller_context_active"] = _controller_context_active(
                    active_game_lease, profile_source
                )
                if time.monotonic() < retry_at:
                    status.update({"vision_state": "error", "vision_error": vision_error or "Camera unavailable; retrying"})
                else:
                    if vision_job is None:
                        startup_timer = time.monotonic()
                        vision_job = _background_call(_prepare_vision, args)
                        vision_operation = "open"
                        vision_started_at = time.time()
                    status.update({"vision_state": "starting", "vision_started_at": vision_started_at})
                status_publisher.submit(status, clear_frame=True)
                matrix.set_status(MatrixStatus.ERROR if vision_error else (
                    (MatrixStatus.TUNING if shared.tuning.active() else MatrixStatus.LEARNING) if practice_mode else MatrixStatus.LOADING))
                time.sleep(0.01)
                continue

            if engine is None:
                engine_base_config = _load_config(args.config)
                engine = GestureEngine(
                    vision_profile, shared.tuning.configuration(engine_base_config),
                    calibration=retained_calibration,
                    rapid_a=None if practice_mode else current_rapid_a,
                    rapid_b=None if practice_mode else current_rapid_b,
                )
            captured_frame = capture.latest_after(last_capture_sequence)
            if captured_frame is None:
                time.sleep(0.001)
                continue
            previous_capture_sequence = last_capture_sequence
            last_capture_sequence = captured_frame.sequence
            capture_skipped_total += max(
                0, captured_frame.sequence - previous_capture_sequence - 1
            )
            if not captured_frame.ok:
                read_failures += 1
                if capture_failure_since is None:
                    capture_failure_since = captured_frame.captured_at
                if time.monotonic() - capture_failure_since >= 2.0:
                    vision_job = _background_call(_close_vision, capture, tracker)
                    vision_operation = "close"
                    capture = tracker = engine = cv2 = None
                    retry_at = time.monotonic() + 1.0
                    vision_error = "Camera stopped delivering frames; reconnecting"
                    status = _base_status(
                        current_profile, current_game, profile_source,
                        controller_enabled, practice_mode=practice_mode,
                        emulator=current_emulator,
                        rapid_a=current_rapid_a, rapid_b=current_rapid_b,
                    )
                    status.update(active_game_lease.snapshot(time.monotonic()))
                    status["controller_context_active"] = _controller_context_active(
                        active_game_lease, profile_source
                    )
                    status.update({"vision_state": "error", "vision_error": vision_error})
                    status_publisher.submit(status, clear_frame=True)
                    matrix.set_status(MatrixStatus.ERROR)
                else:
                    time.sleep(0.005)
                continue
            read_failures = 0
            capture_failure_since = None
            frame = captured_frame.frame
            inference_started = time.monotonic()
            capture_ready_at = getattr(captured_frame, "ready_at", None)
            if capture_ready_at is None:
                capture_ready_at = captured_frame.captured_at
            capture_age_ms = max(
                0.0, (inference_started - captured_frame.captured_at) * 1000
            )
            capture_ready_age_ms = max(
                0.0, (inference_started - capture_ready_at) * 1000
            )
            capture_interval_ms = (
                None if last_capture_at is None
                else max(0.0, (captured_frame.captured_at - last_capture_at) * 1000)
            )
            inference_interval_ms = (
                None if last_inference_started is None
                else max(0.0, (inference_started - last_inference_started) * 1000)
            )
            last_capture_at = captured_frame.captured_at
            last_inference_started = inference_started
            preview_watched = shared.has_stream_clients()
            preview_due = preview_watched and inference_started >= preview_at
            tuning_active = shared.tuning.active()
            needs_center = shared.tuning.needs_center()
            # Resolve the immutable tuning view before inference. Dashboard
            # readers may inspect tuning concurrently, but no tuning lock is
            # allowed between completed inference and controller transmission.
            engine.config = shared.tuning.configuration(engine_base_config)
            tracker.preview_enabled = preview_due
            # Landmark diagnostics are required by personalisation, but the
            # ordinary camera preview already draws directly from the tracker.
            tracker.diagnostics_enabled = tuning_active
            native_xy_active = _native_xy_active(
                engine, practice_mode, tuning_active, needs_center, current_emulator
            )
            result = tracker.process(frame, captured_frame.captured_at)
            tracking_finished_ns = time.monotonic_ns() if trace and trace.enabled else None
            if startup_timer is not None:
                log_startup_stage("first inference", inference_started)
            state, native_source = _update_controller_state(
                engine, result, native_xy_active
            )
            if engine.calibrated and engine.calibration is not retained_calibration:
                retained_calibration = engine.calibration
                try:
                    save_calibration(calibration_path, retained_calibration)
                    shared.tuning.finish_center(retained_calibration)
                    calibration_save_error = None
                except OSError as exc:
                    calibration_save_error = str(exc)
                    print(f"Calibration retained in memory but not saved: {exc}", file=sys.stderr, flush=True)
            inference_finished = time.monotonic()
            # Gameplay output takes priority over matrix RPC and browser preview work.
            launch_guard_active = _launch_guard_active(launch_guard_until)
            controller_context_active = _controller_context_active(
                active_game_lease, profile_source
            )
            receiver_available = sender.send(state) if (
                controller_enabled and not practice_mode and not tuning_active
                and not needs_center
                and controller_context_active and not launch_guard_active
            ) else False
            sent_at = time.monotonic()
            if trace and trace.enabled:
                trace.record(dict(event="vision", session=session_key(sender.session),
                    sequence=state.sequence, capture_sequence=captured_frame.sequence,
                    capture_ns=int(captured_frame.captured_at * 1e9),
                    capture_ready_ns=int(capture_ready_at * 1e9),
                    start_ns=int(inference_started * 1e9), tracking_end_ns=tracking_finished_ns,
                    end_ns=int(inference_finished * 1e9),
                    sent=receiver_available, detected=state.detected, calibrated=state.calibrated,
                    native_xy_source=native_source,
                    **_native_trace_fields(engine, result, native_xy_active),
                    filtered_xy=[engine._filtered_palm_x, engine._filtered_palm_y] if state.detected else None,
                    smoothing={"minimum": engine.config.coordinate_smoothing_min,
                               "maximum": engine.config.coordinate_smoothing_max,
                               "motion_boost": engine.config.coordinate_motion_boost,
                               "native_curve": "bounded_speed",
                               "noise_multiplier": engine.config.motion_noise_multiplier,
                               "noise_floor": engine.config.motion_noise_floor,
                               "noise_exit_ratio": engine.config.motion_noise_exit_ratio,
                               "slow_follow": engine.config.motion_slow_follow,
                               "full_speed": engine.config.motion_full_speed},
                    x=state.axes.get("x", 0), y=state.axes.get("y", 0),
                    buttons=sum(1 << i for i, name in enumerate(("a", "b", "start", "select",
                        "glove_zap", "menu_guard", "closed_hand", "index_point")) if state.buttons.get(name))))
            inference_ms = (inference_finished - inference_started) * 1000
            send_ms = (sent_at - inference_finished) * 1000
            sample_age_ms = max(0.0, (sent_at - captured_frame.captured_at) * 1000)
            signature = _controller_signature(state)
            transition_age_ms = None
            if receiver_available and signature != last_controller_signature:
                transition_age_ms = sample_age_ms
            if receiver_available:
                last_controller_signature = signature
            performance.record(
                capture_age_ms=capture_age_ms,
                capture_ready_age_ms=capture_ready_age_ms,
                capture_interval_ms=capture_interval_ms,
                inference_ms=inference_ms,
                inference_interval_ms=inference_interval_ms,
                send_ms=send_ms,
                sample_age_ms=sample_age_ms,
                controller_transition_age_ms=transition_age_ms,
            )
            statistics_requested = shared.statistics_requested()
            easter_egg = engine.easter_egg_feedback()
            dashboard_signature = _dashboard_event_signature(
                state, receiver_available, controller_enabled,
                controller_context_active, launch_guard_active,
                practice_mode, tuning_active, native_source,
                engine.rapid_a, engine.rapid_b,
                easter_egg["spock_sequence"],
            )
            status_due = dashboard_cadence.due(
                sent_at, dashboard_signature,
                force=practice_mode or tuning_active,
            )
            if not status_due:
                if preview_due:
                    preview_at = time.monotonic() + 1.0 / max(1.0, args.preview_fps)
                    preview_encoder.submit(
                        result.frame,
                        "PRACTICE" if practice_mode else (
                            "CALIBRATING - hold still" if not engine.calibrated
                            else vision_profile.replace("_", " ").upper()
                        ),
                        (0, 210, 255) if not engine.calibrated else (255, 255, 255),
                        cv2, result.preview_overlay,
                        None if practice_mode or tuning_active else 320,
                        mirror=tracker.mirror,
                    )
                continue
            detail_refresh = (
                practice_mode or tuning_active or
                (statistics_requested and (
                    sent_at >= detailed_status_at or signature != last_detail_signature
                ))
            )
            if detail_refresh:
                recognition = engine.recognition_feedback()
                push_feedback = engine.push_feedback(result.observation)
                pull_feedback = engine.pull_feedback(result.observation)
                recognized = [name for name, active in state.dpad.items() if active]
                recognized.extend(name for name, active in state.buttons.items() if active)
                recognized.extend(name for name, active in recognition.items() if active)
                if push_feedback["active"]:
                    recognized.append("push")
                if pull_feedback["active"]:
                    recognized.append("pull")
                detailed_status = {
                    "menu_gesture": engine.menu_feedback(),
                    "push_gesture": push_feedback,
                    "pull_gesture": pull_feedback,
                    "finger_active": engine.curl_feedback(result.observation),
                    "recognition": recognition,
                    "finger_curls": result.observation.fingers,
                    "curl_threshold": engine.config.pair("index")[0],
                }
                detailed_status_at = sent_at + 0.1
                last_detail_signature = signature
                if practice_mode or tuning_active:
                    image_quality = _academy_image_quality(
                        result.frame, result.diagnostics, cv2
                    ) if tuning_active else {}
                    shared.tuning.observe(
                        result.observation, engine.calibration, engine.config,
                        engine.calibrated, frame=result.frame,
                        image_quality=image_quality,
                        performance={"inference_ms": inference_ms,
                                     "sample_age_ms": sample_age_ms},
                        recognized=recognized,
                    )
            matrix.set_status(
                (MatrixStatus.TUNING if shared.tuning.active() else MatrixStatus.LEARNING)
                if practice_mode
                else (
                    MatrixStatus.TRACKING
                    if state.detected and state.calibrated
                    else MatrixStatus.READY
                )
            )
            status = state.to_status_dict()
            if not (statistics_requested or practice_mode or tuning_active):
                for optional in ("axes", "dpad", "buttons", "fingers", "events"):
                    status.pop(optional, None)
            # Raw camera coordinates let reach calibration avoid filtered/clipped axes.
            if practice_mode or tuning_active:
                status["palm_position"] = (
                    {"x": result.observation.palm_x, "y": result.observation.palm_y}
                    if result.observation.detected else None
                )
            grid = _joystick_grid_status(engine, practice_mode, needs_center or bool(calibration_save_error))
            if grid is not None:
                status["joystick_grid"] = grid
            status["inference_ms"] = round(inference_ms, 1)
            status["send_ms"] = round(send_ms, 1)
            status["sample_age_ms"] = round(sample_age_ms, 1)
            status["tracker_backend"] = tracker.backend
            status["tracker_backend_label"] = tracker.backend_label
            status["confidence_source"] = result.observation.confidence_source
            status["inference_threads"] = args.inference_threads
            status["tracking_confidence"] = tracker.tracking_confidence
            status["detection_confidence"] = tracker.detection_confidence
            status["tracking_roi_scale"] = tracker.tracking_roi_scale
            status["tracking_evidence"] = tracker.tracking_evidence
            status["tracker_graph"] = tracker.graph_mode
            status["palm_anchor"] = PALM_ANCHOR
            status.update({
                name: result.diagnostics[name]
                for name in TRACKING_STATUS_FIELDS
                if name in result.diagnostics
            })
            status.update(capture.metadata)
            status["capture_sequence"] = captured_frame.sequence
            status["capture_age_ms"] = round(capture_age_ms, 1)
            status["capture_ready_age_ms"] = round(capture_ready_age_ms, 1)
            status["capture_interval_ms"] = (
                None if capture_interval_ms is None else round(capture_interval_ms, 1)
            )
            status["capture_skipped_total"] = capture_skipped_total
            status["inference_interval_ms"] = (
                None if inference_interval_ms is None else round(inference_interval_ms, 1)
            )
            status["inference_hz"] = (
                None if not inference_interval_ms else round(1000.0 / inference_interval_ms, 1)
            )
            if statistics_requested:
                if sent_at >= performance_snapshot_at:
                    performance_snapshot = performance.snapshot()
                    performance_snapshot_at = sent_at + 0.5
                status["performance"] = performance_snapshot
                status.update(preview_encoder.metrics())
            status["calibration_save_error"] = calibration_save_error
            status["easter_egg"] = easter_egg
            status["calibration_retained"] = retained_calibration is not None
            status["calibrating"] = bool(engine is not None and not engine.calibrated)
            status["game"] = current_game
            status["active_profile"] = current_profile or "off"
            status["vision_profile"] = vision_profile
            status["practice_mode"] = practice_mode
            status["profile_source"] = profile_source
            status["emulator"] = current_emulator
            status["input_mode"] = _input_mode(current_profile, current_emulator)
            default_a, default_b = rapid_fire_defaults(current_profile or "off")
            status["rapid_fire"] = {
                "a": engine.rapid_a, "b": engine.rapid_b,
                "default_a": default_a, "default_b": default_b,
                "override_a": current_rapid_a, "override_b": current_rapid_b,
            }
            program_feedback = engine.program_feedback(state)
            if program_feedback:
                status["program_feedback"] = program_feedback
            status["receiver_available"] = receiver_available
            status["receiver_active_address"] = getattr(sender, "active_address", None)
            status["receiver_error"] = (
                "Practice mode; controller transmission is paused"
                if practice_mode
                else (
                    "RetroPie launch guard; controller transmission is paused"
                    if controller_enabled and launch_guard_active
                    else (
                        "Armed; waiting for a registered game or manual profile"
                        if controller_enabled and not controller_context_active
                        else (sender.last_error if controller_enabled else "Controller connection stopped")
                    )
                )
            )
            status["launch_guard_active"] = launch_guard_active
            status["launch_guard_remaining_ms"] = max(
                0, round((launch_guard_until - time.monotonic()) * 1000)
            )
            status.update(active_game_lease.snapshot(time.monotonic()))
            status["controller_enabled"] = controller_enabled
            status["controller_context_active"] = controller_context_active
            status["camera_available"] = True
            status["vision_state"] = "active"
            if statistics_requested or practice_mode or tuning_active:
                status.update(detailed_status)
            status["native_xy_source"] = native_source
            # Publish control feedback every inference; encode previews asynchronously.
            status_publisher.submit(status)
            if startup_timer is not None:
                log_startup_stage("activation to active status", startup_timer)
                startup_timer = None
            if not preview_due:
                continue
            preview_at = time.monotonic() + 1.0 / max(1.0, args.preview_fps)
            preview_encoder.submit(
                result.frame,
                "PRACTICE" if practice_mode else (
                    "CALIBRATING - hold still" if not engine.calibrated else vision_profile.replace("_", " ").upper()
                ),
                (0, 210, 255) if engine is not None and not engine.calibrated else (255, 255, 255),
                cv2,
                result.preview_overlay,
                None if practice_mode or tuning_active else 320,
                mirror=tracker.mirror,
            )
    except KeyboardInterrupt:
        matrix.set_status(MatrixStatus.OFF)
        return 0
    except Exception:
        matrix.set_status(MatrixStatus.ERROR)
        raise
    finally:
        if engine is not None and controller_enabled and not practice_mode:
            sender.send(ControllerState.released(
                2_147_483_647, time.monotonic(), engine.profile, engine.calibrated
            ))
        # A driver call may be stuck. The process owns its resources and the supervisor
        # can terminate it; never race cleanup against an in-flight I/O operation.
        if vision_job is None:
            _close_vision(capture, tracker)
        sender.close()
        preview_encoder.close()
        status_publisher.close()
        profile_server.close()
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
