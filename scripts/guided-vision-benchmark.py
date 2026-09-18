#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/guided-vision-benchmark.py
# Purpose: Capture a user-paced, labeled vision benchmark with a live preview.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added production-matched direct capture, fast sweeps, and transient-frame retry.
#   2026-09-05 - Added user-paced benchmark capture with browser preview.
# Full history: docs/CHANGELOG.md and Git history.

"""Serve a live preview and capture each benchmark gesture when the user is ready."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virtualglove.camera import camera_candidates  # noqa: E402


CUES = (
    ("neutral_near", "Neutral hand — near", "Sit near the camera with a relaxed open hand centered.", 3.0),
    ("slow_xy", "Slow X/Y sweep", "Move slowly across the useful width and height of the camera view.", 4.0),
    ("fast_xy", "Fast X/Y sweep", "Move quickly left/right and up/down while remaining visible.", 4.0),
    ("short_directions", "Short directions", "Make short left, right, up, and down movements from center.", 4.0),
    ("a", "A — index curl", "Keep the palm visible and curl only the index finger.", 3.0),
    ("b", "B — thumb curl", "Keep the other fingers open and curl the thumb toward the palm.", 3.0),
    ("roll_left", "Roll left", "Keep the hand centered and roll the wrist left.", 3.0),
    ("roll_right", "Roll right", "Return to neutral, then roll the wrist right.", 3.0),
    ("closed_hand", "Closed hand", "Curl the thumb and all four fingers into a comfortable closed hand.", 3.0),
    ("push", "Glove Zap — push", "Begin at neutral distance, then push toward the camera without leaving the frame.", 4.0),
    ("pull", "Pull Back", "Begin at neutral distance, then move away while keeping the palm visible.", 4.0),
    ("tracking_recovery", "Tracking recovery", "Remove the hand completely, pause, then return it to center.", 4.0),
    ("neutral_far", "Neutral hand — farther", "Stand farther away with a relaxed open hand centered.", 3.0),
    ("a_b_far", "A then B — farther", "At the farther position, curl index for A, release, then curl thumb for B.", 4.0),
    ("neutral_finish", "Neutral finish", "Finish with a relaxed open hand and remain still.", 3.0),
)

TRACKING_CUES = tuple(
    cue for cue in CUES
    if cue[0] in ("neutral_near", "slow_xy", "fast_xy", "tracking_recovery", "neutral_finish")
)

FAST_SWEEP_CUES = (
    ("neutral_start", "Neutral start", "Hold a relaxed open hand near the saved centre.", 2.0),
    ("fast_xy", "Fast X/Y sweeps", "Repeat quick left/right, up/down, and diagonal sweeps while keeping the whole hand visible.", 8.0),
    ("neutral_finish", "Neutral finish", "Return to centre and hold the open hand still.", 2.0),
)


PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>VirtualGlove Guided Capture</title><style>
body{margin:0;background:#070a11;color:#eef4ff;font:17px system-ui,sans-serif}main{max-width:1040px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:22px}.camera{width:100%;aspect-ratio:4/3;object-fit:contain;background:#000;border:2px solid #26d6e6;border-radius:14px}.card{background:#121827;border:1px solid #29344d;border-radius:14px;padding:20px}h1,h2{margin-top:0}.step{color:#83edf4;font-weight:700}.phase{font-size:32px;font-weight:800;margin:18px 0}.instruction{min-height:100px;line-height:1.45}.bar{height:12px;background:#222c41;border-radius:9px;overflow:hidden;margin:18px 0}.bar i{display:block;height:100%;background:#31d9e8;width:0}.controls{display:flex;gap:10px;flex-wrap:wrap}button{font:inherit;font-weight:700;padding:11px 16px;border:0;border-radius:9px;background:#31d9e8;color:#071018;cursor:pointer}button.secondary{background:#303b53;color:#fff}button:disabled{opacity:.4;cursor:default}.tip{color:#acb8cd;font-size:14px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style></head><body><main><h1>Guided gesture capture</h1><p>Confirm the pose in the live view, then select <b>Record this step</b>. A two-second countdown precedes each sample.</p><div class=grid><img class=camera src=/stream alt='Live camera preview'><section class=card><div class=step id=step>Loading…</div><h2 id=title>Camera starting</h2><div class=instruction id=instruction></div><div class=phase id=phase>—</div><div class=bar><i id=bar></i></div><div class=controls><button id=record>Record this step</button></div><p class=tip id=tip>Nothing is recorded until you select the button.</p></section></div></main><script>
const q=id=>document.getElementById(id);let priorPhase='';let priorCue=-1;
async function command(path){q('record').disabled=true;await fetch(path,{method:'POST'});}
q('record').onclick=()=>command('/capture');
function speak(text){if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(text));}}
async function update(){try{const s=await(await fetch('/status',{cache:'no-store'})).json();q('step').textContent=s.complete?'Capture complete':`Step ${s.index+1} of ${s.total}`;q('title').textContent=s.title;q('instruction').textContent=s.instruction;q('phase').textContent=s.phase==='ready'?'Ready when you are':s.phase==='countdown'?`Starting in ${Math.ceil(s.remaining)}…`:s.phase==='recording'?`Recording — ${s.remaining.toFixed(1)}s`:'Complete';q('bar').style.width=`${s.progress*100}%`;q('record').disabled=s.phase!=='ready'||s.complete;q('tip').textContent=s.complete?'The labeled clip is saved locally on the UNO Q.':s.phase==='ready'?'Adjust the pose until it looks right, then record this step.':'Hold or perform the instructed movement now.';if(s.index!==priorCue||s.phase!==priorPhase){if(s.phase==='countdown')speak('Get ready. '+s.title);if(s.phase==='recording')speak('Record now');if(s.complete)speak('Capture complete');priorCue=s.index;priorPhase=s.phase}}catch(e){q('phase').textContent='Recorder disconnected'}setTimeout(update,150)}update();
</script></body></html>"""


class GuidedCapture:
    """Capture user-confirmed cues while continuously publishing a live preview."""

    def __init__(self, camera: str, output: Path, width: int, height: int,
                 fps: float, cues: tuple = CUES, *, capture_backend: str = "opencv",
                 camera_buffers: int = 1, manual_exposure: int | None = None,
                 manual_gain: int | None = None) -> None:
        import cv2
        self.cv2 = cv2
        self.output = output
        self.width, self.height, self.fps = width, height, fps
        self.cues = cues
        self.lock = threading.Lock()
        self.release_lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.index = 0
        self.phase = "ready"
        self.phase_started = time.monotonic()
        self.latest_jpeg: bytes | None = None
        self.frames = 0
        self.frame_times: list[float] = []
        self.cue_records: list[dict] = []
        self.timeline = 0.0
        self.complete = False
        self.closed = False
        self.camera_released = False
        self.capture_metadata = {}
        self.capture = self._open_camera(
            camera, capture_backend, camera_buffers, manual_exposure, manual_gain,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        self.writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
        if not self.writer.isOpened():
            self.capture.release()
            raise RuntimeError("Could not create guided benchmark clip")
        threading.Thread(target=self._camera_loop, name="guided-camera", daemon=True).start()

    def _open_camera(self, selection: str, capture_backend: str,
                     camera_buffers: int, manual_exposure: int | None,
                     manual_gain: int | None):
        """Open the first matching camera using low-latency capture settings."""
        cv2 = self.cv2
        manual = manual_exposure is not None or manual_gain is not None
        if manual and (manual_exposure is None or manual_gain is None):
            raise ValueError("manual capture requires both exposure and gain")
        if manual and capture_backend != "direct-v4l2":
            raise ValueError("manual capture requires the direct V4L2 reader")
        for device in camera_candidates(selection):
            backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
            candidate = cv2.VideoCapture(device, backend)
            candidate.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            candidate.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            candidate.set(cv2.CAP_PROP_FPS, self.fps)
            candidate.set(cv2.CAP_PROP_BUFFERSIZE, camera_buffers)
            if candidate.isOpened():
                ok, _frame = candidate.read()
                if not ok:
                    candidate.release()
                    continue
                if capture_backend == "opencv":
                    self.capture_metadata = {"capture_backend": "opencv"}
                    return candidate
                if not sys.platform.startswith("linux"):
                    candidate.release()
                    raise RuntimeError("direct V4L2 capture requires Linux")
                path = (
                    f"/dev/video{int(device)}"
                    if isinstance(device, int) or str(device).isdigit()
                    else str(device)
                )
                candidate.release()
                from virtualglove.v4l2_capture import DirectV4L2Capture
                import numpy
                direct = DirectV4L2Capture(path, camera_buffers, cv2, numpy)
                ok = False
                deadline = time.monotonic() + 5.0
                while not ok and time.monotonic() < deadline:
                    ok, _frame, _captured_at = direct.read_with_timestamp()
                if not ok:
                    direct.close()
                    raise RuntimeError("direct V4L2 produced no benchmark frame")
                self.capture_metadata = {
                    "capture_backend": "direct-v4l2",
                    "camera_buffers": direct.actual_buffers,
                }
                if manual:
                    from virtualglove.camera_controls import (
                        configure_manual_on_fd, restore_automatic_on_fd,
                    )
                    report = configure_manual_on_fd(
                        direct.fd, int(manual_exposure), int(manual_gain),
                    )
                    if not report.get("applied"):
                        restore_automatic_on_fd(direct.fd)
                        direct.close()
                        raise RuntimeError(
                            report.get("reason", "camera rejected manual benchmark settings")
                        )
                    direct.before_close = restore_automatic_on_fd
                    self.capture_metadata.update({
                        "camera_exposure": "manual",
                        "camera_manual_exposure": int(manual_exposure),
                        "camera_manual_gain": int(manual_gain),
                    })
                return direct
            candidate.release()
        raise RuntimeError("No selected camera could be opened")

    def _release_camera(self) -> None:
        """Release either camera backend and restore temporary controls."""
        with self.release_lock:
            if self.camera_released:
                return
            self.camera_released = True
            self.capture.release()
            close = getattr(self.capture, "close", None)
            if close is not None:
                close()

    def _camera_loop(self) -> None:
        """Continuously preview frames and retain only explicitly started cues."""
        cv2 = self.cv2
        preview_at = 0.0
        last_frame_at = time.monotonic()
        while True:
            try:
                ok, frame = self.capture.read()
            except RuntimeError:
                # Direct V4L2 rejects malformed MJPEG buffers explicitly. Treat
                # one like an ordinary read gap so a transient camera frame
                # cannot abort an otherwise healthy user-paced capture.
                ok, frame = False, None
            if not ok:
                if time.monotonic() - last_frame_at < 5.0:
                    time.sleep(.005)
                    continue
                break
            last_frame_at = time.monotonic()
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            now = time.monotonic()
            finished = False
            with self.lock:
                if self.closed:
                    break
                if self.phase == "countdown" and now - self.phase_started >= 2.0:
                    self.phase = "recording"
                    self.phase_started = now
                    label, title, instruction, duration = self.cues[self.index]
                    self.cue_records.append({"start": self.timeline, "end": self.timeline + duration,
                                             "label": label, "instruction": instruction})
                if self.phase == "recording":
                    duration = self.cues[self.index][3]
                    elapsed = now - self.phase_started
                    if elapsed < duration:
                        self.writer.write(frame)
                        self.frames += 1
                        self.frame_times.append(round(self.timeline + elapsed, 6))
                    else:
                        self.timeline += duration
                        self.index += 1
                        if self.index >= len(self.cues):
                            self.complete = True
                            self.phase = "complete"
                            self._finish_locked()
                            finished = True
                        else:
                            self.phase = "ready"
                            self.phase_started = now
                if now >= preview_at:
                    preview = frame.copy()
                    cv2.putText(preview, self.cues[min(self.index, len(self.cues)-1)][1], (16, 34),
                                cv2.FONT_HERSHEY_SIMPLEX, .75, (255, 255, 255), 2, cv2.LINE_AA)
                    encoded, data = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 76])
                    if encoded:
                        self.latest_jpeg = data.tobytes()
                        self.condition.notify_all()
                    preview_at = now + .1
            if finished:
                break
        self._release_camera()
        with self.lock:
            if not self.complete:
                self._finish_locked()

    def _finish_locked(self) -> None:
        """Close the clip and write its cue-aligned local metadata sidecar."""
        if self.writer is None:
            return
        self.writer.release()
        self.writer = None
        sidecar = self.output.with_suffix(self.output.suffix + ".json")
        sidecar.write_text(json.dumps({
            "version": 2, "clip": str(self.output), "local_only": True,
            "width": self.width, "height": self.height, "fps": self.fps,
            "frames": self.frames, "duration_seconds": self.timeline,
            "effective_fps": round(self.frames / self.timeline, 6) if self.timeline else 0,
            "frame_times_seconds": self.frame_times, "cues": self.cue_records,
            "capture": getattr(self, "capture_metadata", {}),
        }, indent=2) + "\n")

    def start(self) -> None:
        """Begin the visible countdown for the current ready cue."""
        with self.lock:
            if self.phase == "ready" and not self.complete:
                self.phase = "countdown"
                self.phase_started = time.monotonic()

    def status(self) -> dict:
        """Return browser-safe progress for the current capture cue."""
        with self.lock:
            index = min(self.index, len(self.cues) - 1)
            label, title, instruction, duration = self.cues[index]
            elapsed = time.monotonic() - self.phase_started
            remaining = max(0.0, (2.0 if self.phase == "countdown" else duration) - elapsed)
            progress = 0.0 if self.phase == "ready" else (
                min(1.0, elapsed / 2.0) if self.phase == "countdown" else
                min(1.0, elapsed / duration) if self.phase == "recording" else 1.0
            )
            return {"index": index, "total": len(self.cues), "label": label, "title": title,
                    "instruction": instruction, "phase": self.phase, "remaining": remaining,
                    "progress": progress, "complete": self.complete, "frames": self.frames}

    def close(self) -> None:
        """Stop capture and release the camera and writer idempotently."""
        with self.lock:
            self.closed = True
            self._finish_locked()
        self._release_camera()


def handler(capture: GuidedCapture):
    """Create a request handler bound to one guided capture session."""

    class Handler(BaseHTTPRequestHandler):
        """Serve the local capture UI, status, preview, and start action."""

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/status":
                self._send(200, json.dumps(capture.status()).encode(), "application/json")
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                last = None
                try:
                    while True:
                        with capture.condition:
                            capture.condition.wait_for(lambda: capture.latest_jpeg is not last, timeout=1)
                            jpeg = capture.latest_jpeg
                        if jpeg is None or jpeg is last:
                            continue
                        last = jpeg
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/capture":
                capture.start()
                self._send(204, b"", "text/plain")
            else:
                self.send_error(404)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            """Write a bounded no-store HTTP response."""
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            pass

    return Handler


def main() -> int:
    """Start the local guided-capture web server until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", default="auto")
    parser.add_argument("--output", type=Path, default=Path("/tmp/virtualglove-guided-benchmark.avi"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--protocol", choices=("full", "tracking", "fast-sweep"), default="full")
    parser.add_argument("--capture-backend", choices=("opencv", "direct-v4l2"), default="opencv")
    parser.add_argument("--camera-buffers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--manual-exposure", type=int)
    parser.add_argument("--manual-gain", type=int)
    args = parser.parse_args()
    cues = (TRACKING_CUES if args.protocol == "tracking" else
            FAST_SWEEP_CUES if args.protocol == "fast-sweep" else CUES)
    guided = GuidedCapture(
        args.camera, args.output, args.width, args.height, args.fps, cues,
        capture_backend=args.capture_backend, camera_buffers=args.camera_buffers,
        manual_exposure=args.manual_exposure, manual_gain=args.manual_gain,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler(guided))
    print(f"Guided capture: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        guided.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
