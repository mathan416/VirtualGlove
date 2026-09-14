# Project: VirtualGlove
# File: python/main.py
# Purpose: Supervise the UNO Q App Lab vision worker, web controls, model retrieval, and camera recovery.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-10 - Reaped the complete uv/Python/camera worker process group on restart.
#   2026-09-10 - Allowed opt-in process isolation with OpenCV capture.
#   2026-09-10 - Prefer the retained worker cache while preserving first-install online fallback.
#   2026-09-09 - Added validated opt-in process-isolated direct capture.
#   2026-09-09 - Made validated MediaPipe 0.10.35 the sole worker runtime.
#   2026-09-09 - Verify camera recovery only after the restarted worker receives a frame.
#   2026-09-07 - Pass optional direct capture and capability-checked exposure settings.
#   2026-09-07 - Pass an explicit validated MediaPipe inference thread count.
#   2026-09-06 - Support measured opt-in Kiyo Pro capture controls and buffer count.
#   2026-09-06 - Add opt-in independent native hand movement tracking.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-06 - Add a persistent idle attract setting without restarting vision.
#   2026-09-06 - Publish the running matrix firmware identity outside the worker.
#   2026-09-05 - Request one guarded host USB reset after a sustained camera outage.
#   2026-09-05 - Selected the deployed legacy-lite tracker explicitly.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Delegated idle and active vision lifecycle to the persistent worker.
#   2026-09-03 - Displayed a dedicated matrix state during Learn sessions.
#   2026-09-03 - Support an unconfigured first-run receiver without blocking local practice.

"""Arduino App Lab entry point for VirtualGlove."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = APP_ROOT / "data" / "device.json"
sys.path.insert(0, str(APP_ROOT / "src"))

def _shutdown_on_signal(_signum: int, _frame: object) -> None:
    """Convert process termination into the supervisor's normal cleanup path."""
    raise KeyboardInterrupt


def _stop_worker(process: subprocess.Popen, timeout: float = 7.0) -> None:
    """Stop and reap the complete uv/Python/camera worker process group."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def load_device_config() -> dict:
    """Load persistent device settings, creating safe first-run defaults when absent."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    # A useful, portable first-run default. The same token must be copied to
    # the RetroPie receiver before controller packets will be accepted.
    settings = {
        "receiver": "",
        "token": secrets.token_urlsafe(24),
        "profile": "off",
        "glove_color": "none",
        "camera": "auto",
        "matrix_attract": "on",
        "inference_threads": 4,
        "tracking_confidence": 0.35,
        "detection_confidence": 0.45,
        "tracking_roi_scale": 2.25,
        "camera_fps": "auto",
        "camera_buffers": 1,
        "camera_backend": "opencv",
        "capture_isolation": "thread",
        "camera_exposure": "auto",
        "camera_manual_exposure": 78,
        "camera_manual_gain": 96,
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    from powerglove_vision.game_registry import atomic_write
    atomic_write(CONFIG_PATH, json.dumps(settings, indent=2) + "\n")
    return settings


def worker_runtime_prefix() -> list[str]:
    """Build the uv prefix shared by worker launches and the offline probe."""
    wheel = next(
        (APP_ROOT / "python" / "worker-wheels").glob(
            "mediapipe-0.10.35+powerglove*.whl"
        )
    )
    return [
        # The repository supports the RetroPie receiver on Python 3.7, while
        # MediaPipe requires a newer interpreter. Keep the worker resolution
        # independent of project-wide Python compatibility metadata.
        "uv", "run", "--no-project", "--python", "3.12", "--with", str(wheel),
    ]


def worker_command(settings: dict, model_path: Path, controller_enabled: bool = False) -> list[str]:
    """Build the isolated MediaPipe worker command from validated runtime settings."""
    command = worker_runtime_prefix() + [
        "python", "-m", "powerglove_vision.vision_app",
        "--receiver", str(settings.get("receiver", "")),
        "--port", str(settings.get("port", 55355)),
        "--device-config", str(CONFIG_PATH),
        "--profile", str(settings.get("profile", "off")),
        "--glove-color", str(settings.get("glove_color", "none")),
        "--camera", str(settings.get("camera", "auto")),
        "--camera-format", "MJPG",
        "--tracker-backend", "legacy",
        "--web-host", "127.0.0.1", "--web-port", "8089", "--no-matrix",
    ]
    tracker_graph = settings.get("tracker_graph", "full")
    if tracker_graph not in ("full", "lean-image"):
        tracker_graph = "full"
    command.extend(["--tracker-graph", tracker_graph])
    inference_threads = settings.get("inference_threads", 4)
    if type(inference_threads) is not int or inference_threads not in (1, 2, 4):
        inference_threads = 4
    command.extend(["--inference-threads", str(inference_threads)])
    tracking_confidence = settings.get("tracking_confidence", 0.35)
    if (type(tracking_confidence) not in (int, float)
            or not 0.0 <= tracking_confidence <= 1.0):
        tracking_confidence = 0.35
    command.extend(["--tracking-confidence", str(tracking_confidence)])
    detection_confidence = settings.get("detection_confidence", 0.45)
    if (type(detection_confidence) not in (int, float)
            or not 0.0 <= detection_confidence <= 1.0):
        detection_confidence = 0.45
    command.extend(["--detection-confidence", str(detection_confidence)])
    tracking_roi_scale = settings.get("tracking_roi_scale", 2.25)
    if (type(tracking_roi_scale) not in (int, float)
            or float(tracking_roi_scale) not in (2.0, 2.25)):
        tracking_roi_scale = 2.25
    command.extend(["--tracking-roi-scale", str(float(tracking_roi_scale))])
    camera_fps = settings.get("camera_fps", "auto")
    if camera_fps == "auto":
        requested_fps = 0
    elif type(camera_fps) is int and camera_fps in (30, 60):
        requested_fps = camera_fps
    else:
        requested_fps = 0
    command.extend(["--fps", str(requested_fps)])
    camera_backend = settings.get("camera_backend", "opencv")
    if camera_backend not in ("opencv", "direct-v4l2"):
        camera_backend = "opencv"
    command.extend(["--capture-backend", camera_backend])
    capture_isolation = settings.get("capture_isolation", "thread")
    if capture_isolation not in ("thread", "process"):
        capture_isolation = "thread"
    command.extend(["--capture-isolation", capture_isolation])
    camera_exposure = settings.get("camera_exposure", "auto")
    if settings.get("kiyo_hdr_off") is True:
        camera_exposure = "kiyo-low-latency"
    if camera_exposure not in ("auto", "low-latency", "kiyo-low-latency", "manual"):
        camera_exposure = "auto"
    manual_exposure = settings.get("camera_manual_exposure")
    manual_gain = settings.get("camera_manual_gain")
    manual_valid = (
        camera_backend == "direct-v4l2"
        and type(manual_exposure) is int and 1 <= manual_exposure <= 10_000
        and type(manual_gain) is int and 0 <= manual_gain <= 10_000
    )
    if camera_exposure == "manual" and not manual_valid:
        camera_exposure = "auto"
    command.extend(["--camera-exposure", camera_exposure])
    if camera_exposure == "manual":
        command.extend([
            "--camera-manual-exposure", str(manual_exposure),
            "--camera-manual-gain", str(manual_gain),
        ])
    test_exposure = settings.get("camera_manual_exposure_test")
    test_gain = settings.get("camera_manual_gain_test")
    if (camera_backend == "direct-v4l2"
            and type(test_exposure) is int and 1 <= test_exposure <= 10_000
            and type(test_gain) is int and 0 <= test_gain <= 10_000):
        command.extend([
            "--camera-manual-exposure-test", str(test_exposure),
            "--camera-manual-gain-test", str(test_gain),
        ])
    if settings.get("camera_buffers") == 2:
        command.extend(["--camera-buffers", "2"])
    if controller_enabled:
        command.append("--controller-enabled")
    return command


def prefer_retained_worker_cache(environment: dict[str, str]) -> dict[str, str]:
    """Use the complete local uv cache, or retain online resolution for first install."""
    offline = dict(environment)
    offline["UV_OFFLINE"] = "1"
    try:
        completed = subprocess.run(
            worker_runtime_prefix() + ["python", "-c", "pass"],
            cwd=APP_ROOT,
            env=offline,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return environment
    return offline if completed.returncode == 0 else environment


def main() -> int:
    """Supervise the worker, control server, matrix, camera availability, and clean shutdown."""
    settings = load_device_config()
    from powerglove_vision.matrix import MatrixStatus, UnoQMatrix, status_from_worker
    matrix = UnoQMatrix()
    matrix.set_status(MatrixStatus.LOADING)
    from powerglove_vision.control_server import start_control_server
    from powerglove_vision.camera import CameraRecoveryRequester
    control_server, control = start_control_server(
        CONFIG_PATH, pairing_display=matrix.show_pairing, pairing_finished=matrix.finish_pairing
    )
    camera_recovery = CameraRecoveryRequester(
        APP_ROOT / "data" / ".camera-recovery-enabled",
        APP_ROOT / "data" / "camera-recovery-request",
    )
    matrix.set_profile(str(settings.get("profile", "off")))

    control.connection_probe = matrix.connection_status
    environment = dict(os.environ)
    # App Lab uses a bootstrap virtual environment. The vision worker manages
    # its own Python runtime with uv, so inheriting this emits a false warning.
    environment.pop("VIRTUAL_ENV", None)
    environment.update({
        "PYTHONPATH": str(APP_ROOT / "src"),
        "UV_CACHE_DIR": str(APP_ROOT / "data" / "uv-cache"),
        "UV_PYTHON_INSTALL_DIR": str(APP_ROOT / "data" / "uv-python"),
    })
    environment = prefer_retained_worker_cache(environment)

    process: subprocess.Popen | None = None
    model_path = APP_ROOT / "data" / "models" / "hand_landmarker.task"
    signal.signal(signal.SIGTERM, _shutdown_on_signal)
    try:
        # The worker keeps its lightweight control plane alive while gestures
        # are paused and owns lazy camera/model activation for active profiles.
        while True:
            settings = control.load_config()
            matrix.set_profile(str(settings.get("profile", "off")))
            matrix.set_status(MatrixStatus.LOADING)
            revision = control.revision
            process = subprocess.Popen(
                worker_command(settings, model_path, control.controller_enabled()), cwd=APP_ROOT,
                env=environment, start_new_session=True,
            )
            control.update_supervisor(camera=False, running=True)
            configuration_changed = False
            camera_recovery_restart = False
            while process.poll() is None:
                if revision != control.revision:
                    configuration_changed = True
                    _stop_worker(process)
                    break
                try:
                    control.flush_controller_request()
                    worker_status_url = "http://127.0.0.1:8089/status"
                    if control.statistics_requested():
                        worker_status_url += "?statistics=1"
                    with urllib.request.urlopen(worker_status_url, timeout=0.3) as response:
                        status = json.load(response)
                    control.update_worker(status)
                    control.update_firmware(matrix.firmware_identity())
                    recovery_requested = camera_recovery.observe(status)
                    verified_method = camera_recovery.consume_verified_recovery()
                    if verified_method is not None:
                        print(
                            "VirtualGlove: camera recovery verified by a test frame "
                            f"after {verified_method}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if recovery_requested:
                        print(
                            "VirtualGlove: requested guarded USB camera preparation/recovery",
                            file=sys.stderr,
                            flush=True,
                        )
                        if camera_recovery.last_action == "recover":
                            # Do not race UVC open/read calls against the host's
                            # physical USB unbind/rebind cycle.
                            camera_recovery_restart = True
                            _stop_worker(process)
                            break
                    active_profile = status.get("active_profile")
                    matrix.set_profile(
                        None if status.get("practice_mode") or active_profile == "off"
                        else active_profile
                    )
                    display_status = status_from_worker(status)
                    matrix.set_attract(control.load_config(), idle=display_status == MatrixStatus.GESTURES_IDLE)
                    matrix.set_status(display_status)
                except (OSError, ValueError, TimeoutError):
                    pass
                time.sleep(0.25)
            process = None
            if camera_recovery_restart:
                matrix.set_status(MatrixStatus.LOADING)
                control.update_supervisor(camera=False, running=True)
                recovered = camera_recovery.wait_for_recovery()
                print(
                    (
                        "VirtualGlove: guarded USB action completed; "
                        "waiting for a camera test frame"
                        if recovered else
                        "VirtualGlove: guarded USB action did not complete"
                    ),
                    file=sys.stderr,
                    flush=True,
                )
                # Let udev finish publishing the returned video nodes before
                # the fresh worker performs camera discovery and UVC setup.
                time.sleep(2.0)
                continue
            if configuration_changed:
                matrix.set_status(MatrixStatus.LOADING)
                control.update_supervisor(camera=False, running=False)
                continue
            matrix.set_status(MatrixStatus.ERROR)
            control.update_supervisor(camera=False, running=False, error="Vision worker stopped; retrying")
            time.sleep(5)
    except KeyboardInterrupt:
        matrix.set_status(MatrixStatus.OFF)
        if process is not None and process.poll() is None:
            _stop_worker(process)
        return 0
    finally:
        control_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
