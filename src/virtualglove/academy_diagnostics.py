# Project: VirtualGlove
# File: src/virtualglove/academy_diagnostics.py
# Purpose: Run privacy-bounded, user-paced Glove Academy diagnostics.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Kept diagnostics compatible with the supported Python 3.7 runtime.
#   2026-09-06 - Added local guided capture with aggregate-only reporting.
# Full history: docs/CHANGELOG.md and Git history.

"""Temporary Academy video capture; only aggregate recognition results survive."""

from __future__ import annotations

import time
from pathlib import Path


CUES = (
    ("neutral", "Relaxed open hand", "Hold your open hand in the centre.", 3.0),
    ("directions", "Short directions", "Move left, right, up, and down from centre.", 4.0),
    ("a_b", "A then B", "Curl index for A, release, then curl thumb for B.", 4.0),
    ("menu", "Start then Select", "Make the V sign, release, then give a thumbs-up.", 4.0),
    ("wrist", "Rolls and closed hand", "Roll left, roll right, then close your hand.", 5.0),
    ("depth", "Glove Zap and Pull Back", "Push, return, pull back, then return.", 5.0),
    ("guard", "Menu guard", "Curl only thumb and ring, then release.", 3.0),
    ("recovery", "Tracking recovery", "Remove your hand, pause, then return it.", 4.0),
)


def _percentile(values: list[float], fraction: float) -> float | None:
    """Return a rounded percentile without retaining the original samples."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 1)


class AcademyDiagnostics:
    """Own one temporary AVI and discard it after aggregate analysis."""

    def __init__(self, directory: Path, clock=time.monotonic) -> None:
        self.directory = Path(directory)
        self.clock = clock
        self.output = self.directory / ".academy-diagnostic.avi"
        self.active = False
        self.index = 0
        self.phase = "idle"
        self.phase_started = 0.0
        self.last_action = 0.0
        self.writer = None
        self.samples: list[list[dict]] = []
        self.report = None

    def _delete_video(self) -> None:
        """Close and remove the sole temporary raw-video artifact."""
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        try:
            self.output.unlink()
        except FileNotFoundError:
            pass

    def expire(self) -> None:
        """Cancel an abandoned capture after its fixed inactivity limit."""
        if self.active and self.clock() - self.last_action >= 1800:
            self.cancel()

    def begin(self) -> None:
        """Start a clean diagnostic session at its first user-paced cue."""
        self.cancel()
        self.active = True
        self.phase = "ready"
        self.last_action = self.clock()
        self.samples = [[] for _ in CUES]
        self.report = None

    def record(self) -> None:
        """Begin recording the current cue when the prior cue is complete."""
        self.expire()
        if not self.active or self.phase != "ready":
            raise ValueError("Finish the current diagnostic step first.")
        self.phase = "recording"
        self.phase_started = self.clock()
        self.last_action = self.phase_started

    def observe(self, frame, sample: dict) -> None:
        """Record one active-cue frame and its aggregate-safe measurements."""
        self.expire()
        if not self.active or self.phase != "recording":
            return
        import cv2
        if self.writer is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            height, width = frame.shape[:2]
            self.writer = cv2.VideoWriter(
                str(self.output), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (width, height)
            )
            if not self.writer.isOpened():
                self.writer = None
                self.cancel()
                raise OSError("Could not create the temporary diagnostic video.")
        self.writer.write(frame)
        self.samples[self.index].append(dict(sample))
        duration = CUES[self.index][3]
        if self.clock() - self.phase_started < duration:
            return
        self.index += 1
        self.last_action = self.clock()
        if self.index >= len(CUES):
            self._finish()
        else:
            self.phase = "ready"

    def _finish(self) -> None:
        """Reduce measurements to aggregates and immediately delete raw video."""
        cue_results = []
        for cue, frames in zip(CUES, self.samples):
            detected = sum(bool(frame.get("detected")) for frame in frames)
            confidences = [float(frame["confidence"]) for frame in frames if frame.get("detected")]
            inference = [float(frame["inference_ms"]) for frame in frames if frame.get("inference_ms") is not None]
            ages = [float(frame["sample_age_ms"]) for frame in frames if frame.get("sample_age_ms") is not None]
            luma = [float(frame["hand_luma"]) for frame in frames if frame.get("hand_luma") is not None]
            recognized = sorted({name for frame in frames for name in frame.get("recognized", [])})
            cue_results.append({
                "label": cue[0], "title": cue[1], "frames": len(frames),
                "detection_percent": round(detected / len(frames) * 100, 1) if frames else 0.0,
                "confidence_mean": round(sum(confidences) / len(confidences), 3) if confidences else None,
                "inference_ms_p50": _percentile(inference, .50),
                "inference_ms_p95": _percentile(inference, .95),
                "sample_age_ms_p95": _percentile(ages, .95),
                "hand_luma_mean": round(sum(luma) / len(luma), 1) if luma else None,
                "recognized": recognized,
            })
        self.report = {
            "version": 1,
            "local_only": True,
            "raw_video_deleted": True,
            "backend": "MediaPipe Hands",
            "summary": cue_results,
        }
        self._delete_video()
        self.active = False
        self.phase = "complete"

    def cancel(self) -> None:
        """Cancel the session and remove all raw and aggregate session state."""
        self._delete_video()
        self.active = False
        self.phase = "idle"
        self.index = 0
        self.samples = []
        self.report = None

    def snapshot(self) -> dict:
        """Return the current cue, progress state, and aggregate report."""
        self.expire()
        index = min(self.index, len(CUES) - 1)
        cue = CUES[index]
        return {
            "active": self.active, "phase": self.phase, "index": index,
            "total": len(CUES), "title": cue[1], "instruction": cue[2],
            "complete": self.phase == "complete", "report": self.report,
        }
