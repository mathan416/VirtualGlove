#!/usr/bin/env python3
"""Replay one VirtualGlove gesture regression recording."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from powerglove_vision.gesture_replay import replay_recording


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify recorded derived hand measurements against expected controls."
    )
    parser.add_argument("recording", type=Path)
    parser.add_argument("--json", action="store_true", help="print the complete JSON report")
    args = parser.parse_args()
    try:
        report = replay_recording(args.recording.read_bytes())
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    elif report["passed"]:
        print(f"PASS: {report['frames']} gesture frames match")
    else:
        first = report["mismatches"][0]
        print(f"FAIL: {report['mismatch_count']} of {report['frames']} frames changed; "
              f"first mismatch at frame {first['frame']} ({first['at_ms']} ms)")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
