#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/analyze-latency-video.py
# Purpose: Measure reviewed hand/screen video annotations using decoded presentation timestamps.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added overview/contact sheets and a bound annotation template.
#   2026-09-06 - Add timestamp validation, onset brackets, and annotated evidence stills.
# Full history: docs/CHANGELOG.md and Git history.

"""Review original video locally with PyAV/Pillow; no camera activation or upload."""
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


def summary(values):
    """Summarize individually measured values, not pooled stage percentiles."""
    if not values:
        return {'samples': 0}
    ordered = sorted(values)
    return dict(samples=len(values), min=min(values), p50=ordered[math.ceil(len(values)*.5)-1],
                p95=ordered[math.ceil(len(values)*.95)-1], max=max(values))


def analyze(times, annotation):
    """Require reviewed visibility/timing and bracket each first-changed frame."""
    if len(times) < 2 or any(not math.isfinite(t) for t in times) or any(b <= a for a,b in zip(times, times[1:])):
        raise ValueError('Missing, duplicate, or non-increasing video presentation timestamps')
    if annotation.get('timing_verified') is not True:
        raise ValueError('Verify original capture timing, including any slow-motion retiming, first')
    scale = annotation.get('seconds_per_pts_second', 1)
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid explicit conversion from file time to real seconds')
    times = [t*scale for t in times]
    intervals = [b-a for a,b in zip(times, times[1:])]
    median = statistics.median(intervals)
    if max(intervals) > median*1.5:
        raise ValueError('Video contains gaps or variable retiming; export a uniform original capture and review again')
    trials, rejected, selected = [], [], set()

    def frame(value):
        """Require an actual decoded frame index with a preceding observation."""
        if type(value) is not int or not 1 <= value < len(times):
            raise ValueError('Frame index must have a preceding decoded frame')
        selected.add(value)
        return value

    for trial in annotation.get('trials', []):
        if trial.get('unoccluded') is not True:
            rejected.append(trial.get('label', 'unlabelled'))
            continue
        hand, game = frame(trial['hand_onset']), frame(trial['game_onset'])
        if game < hand or trial.get('direction') not in ('left', 'right', 'up', 'down'):
            raise ValueError('Invalid movement direction or response before hand onset')
        item = dict(label=trial['label'], direction=trial['direction'],
                    onset_ms=(times[game]-times[hand])*1000,
                    onset_lower_ms=max(0, (times[game-1]-times[hand])*1000),
                    onset_upper_ms=(times[game]-times[hand-1])*1000)
        if 'hand_stop' in trial or 'game_settled' in trial:
            stop, settled = frame(trial['hand_stop']), frame(trial['game_settled'])
            if stop < hand or settled < max(stop, game):
                raise ValueError('Invalid stop/settling frame order')
            item['stop_to_settle_ms'] = (times[settled]-times[stop])*1000
        points = trial.get('trajectory', [])
        if points:
            indices = [frame(point['frame']) for point in points]
            if len(points) < 3 or any(b <= a for a,b in zip(indices, indices[1:])):
                raise ValueError('Following trajectory needs at least three chronological points')
            axis = 'x' if trial['direction'] in ('left', 'right') else 'y'
            progress = {}
            for source in ('hand', 'glove'):
                values = [point[source+'_'+axis] for point in points]
                if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                    raise ValueError('Non-finite trajectory pixel position')
                displacement = values[-1]-values[0]
                if abs(displacement) < 1:
                    raise ValueError('Trajectory must cover one movement through its settled endpoint')
                progress[source] = [(v-values[0])/displacement for v in values]
            item['following'] = dict(samples=len(points),
                normalized_progress_error_rms=math.sqrt(sum((h-g)**2 for h,g in
                    zip(progress['hand'],progress['glove']))/len(points)),
                glove_overshoot_fraction=max(0, max(progress['glove'])-1))
        trials.append(item)
    stationary = []
    for window in annotation.get('stationary', []):
        points = window['points']
        if len(points) < 2:
            raise ValueError('Stationary window needs at least two reviewed positions')
        indices = [frame(point['frame']) for point in points]
        if any(b <= a for a,b in zip(indices, indices[1:])):
            raise ValueError('Stationary positions must be chronological')
        item = dict(label=window['label'], accepted=window.get('unoccluded') is True
                    and window.get('tracking_losses') == 0, positions=len(points),
                    sampled_duration_seconds=times[indices[-1]]-times[indices[0]])
        for name in ('hand_x', 'hand_y', 'glove_x', 'glove_y'):
            values = [point[name] for point in points]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                raise ValueError('Non-finite annotated pixel position')
            item[name] = dict(span=max(values)-min(values), standard_deviation=statistics.pstdev(values))
        stationary.append(item)
    return dict(format='powerglove-video-analysis/1', frame_interval_ms=summary([t*1000 for t in intervals]),
                onset_ms=summary([t['onset_ms'] for t in trials]),
                by_direction={d:summary([t['onset_ms'] for t in trials if t['direction']==d])
                              for d in ('left','right','up','down')},
                trials=trials, rejected_trials=rejected, stationary=stationary,
                limitations=['Onset brackets cover frame sampling only; exposure, rolling shutter and annotation error remain.',
                    'Hand and screen must appear in the SAME recording. No external device clocks are used.',
                    'Pixel positions are manually reviewed samples, not automatically isolated tracker noise.',
                    'Human tremor is included; stationary acceptance also requires matching telemetry review.']), selected


def review_selection(frame_count, explicit='', around='', radius=4, overview=24):
    """Choose bounded review frames without pretending they are detected events."""
    selected = {int(value) for value in explicit.split(',') if value.strip()} if explicit else set()
    centers = {int(value) for value in around.split(',') if value.strip()} if around else set()
    for center in centers:
        selected.update(range(max(0, center-radius), min(frame_count, center+radius+1)))
    if not selected and frame_count:
        count = min(overview, frame_count)
        selected.update(round(index*(frame_count-1)/max(1, count-1)) for index in range(count))
    if len(selected) > 500 or any(index < 0 or index >= frame_count for index in selected):
        raise ValueError('Choose at most 500 existing decoded frames')
    return selected


def annotation_template(digest, protocol, seconds_per_pts_second=1.0,
                        capture_fps=None):
    """Create placeholders that cannot accidentally pass reviewed analysis."""
    directions = ('left', 'right') if protocol == 'smoke' else ('left', 'right', 'up', 'down')
    count = 2 if protocol == 'smoke' else 10
    return {'video_sha256': digest, 'timing_verified': False,
            'seconds_per_pts_second': seconds_per_pts_second,
            'capture_fps_reported': capture_fps,
            'trials': [{'label': '%s-%02d' % (direction, index+1),
                        'direction': direction, 'unoccluded': False,
                        'hand_onset': None, 'game_onset': None}
                       for direction in directions for index in range(count)],
            'stationary': [],
            'instructions': [
                'Verify original recording rate and slow-motion retiming before setting timing_verified true.',
                'Set unoccluded true and replace null indexes only after reviewing both hand and game.',
                'Use --around FRAME to create a tighter frame-by-frame contact sheet.',
            ]}


def build_contact_sheet(paths, destination, columns=4):
    """Combine selected evidence stills into a legible local review sheet."""
    if not paths:
        return
    from PIL import Image, ImageOps
    width = 360
    thumbs = []
    for path in paths:
        with Image.open(path) as source:
            copy = source.convert('RGB')
            height = max(1, round(copy.height * width / copy.width))
            thumbs.append(ImageOps.fit(copy, (width, height)))
    cell_height = max(image.height for image in thumbs)
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new('RGB', (columns*width, rows*cell_height), 'black')
    for index, picture in enumerate(thumbs):
        sheet.paste(picture, ((index % columns)*width, (index // columns)*cell_height))
    sheet.save(destination, compress_level=1)


def main():
    """Index a video or analyse explicit reviewed annotations and extract evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--annotations', type=Path)
    parser.add_argument('--frames', help='Comma-separated zero-based frames to inspect without measuring')
    parser.add_argument('--around', help='Comma-separated centre frames for a frame-by-frame review strip')
    parser.add_argument('--radius', type=int, default=4,
                        help='Frames on each side of every --around centre (default: 4)')
    parser.add_argument('--protocol', choices=('smoke', 'full'), default='full',
                        help='Trial placeholders to put in a new annotation template')
    parser.add_argument('--overview-frames', type=int, default=24,
                        help='Evenly spaced frames in the initial contact sheet (default: 24)')
    parser.add_argument('--capture-fps', type=float,
                        help='Operator-confirmed capture rate; suggests, but never approves, timing scale')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    import av
    from PIL import ImageDraw, ImageOps
    if (not 0 <= args.radius <= 30 or not 4 <= args.overview_frames <= 100
            or args.capture_fps is not None and not 1 <= args.capture_fps <= 1000):
        parser.error('radius must be 0..30, overview-frames 4..100, and capture-fps 1..1000')
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    digest = hashlib.sha256()
    with args.video.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    annotation = json.loads(args.annotations.read_text()) if args.annotations else None
    overview_only = annotation is None and not args.frames and not args.around
    if annotation and annotation.get('video_sha256') != digest.hexdigest():
        parser.error('Annotations must name this original video SHA-256')
    times = []
    display_rotation = None
    with av.open(str(args.video)) as container:
        for frame in container.decode(video=0):
            if frame.pts is None or frame.time_base is None:
                parser.error('Decoded frame has no presentation timestamp')
            times.append(float(frame.pts*frame.time_base))
            rotation = int(frame.rotation or 0)
            if display_rotation is None:
                display_rotation = rotation
            elif rotation != display_rotation:
                parser.error('Video display orientation changes between frames')
            if len(times) > 150000:
                parser.error('Use a shorter recording (maximum 150000 frames)')
    try:
        selected = (set() if annotation and not args.frames and not args.around else
                    review_selection(len(times), args.frames or '', args.around or '',
                                     args.radius, args.overview_frames))
    except ValueError as error:
        parser.error(str(error))
    report = dict(format='powerglove-video-index/1', video_sha256=digest.hexdigest(),
                  frame_count=len(times), presentation_seconds=times,
                  display_rotation_degrees=display_rotation or 0,
                  timing_verified=False, note='Verify real capture rate/retiming before latency analysis')
    if annotation:
        report, evidence = analyze(times, annotation)
        selected.update(evidence)
        report['video_sha256'] = digest.hexdigest()
        report['display_rotation_degrees'] = display_rotation or 0
    if len(selected) > 500 or any(i < 0 or i >= len(times) for i in selected):
        parser.error('Choose at most 500 existing decoded frames')
    elif not annotation:
        encoded_fps = 1.0 / statistics.median(
            b-a for a, b in zip(times, times[1:])
        ) if len(times) > 1 else None
        scale = encoded_fps / args.capture_fps if args.capture_fps and encoded_fps else 1.0
        template = annotation_template(
            digest.hexdigest(), args.protocol, scale, args.capture_fps
        )
        (args.output_dir/'annotations.template.json').write_text(
            json.dumps(template, indent=2, allow_nan=False) + '\n')
    saved = []
    with av.open(str(args.video)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if index not in selected:
                continue
            picture = frame.to_image()
            if display_rotation:
                picture = picture.rotate(display_rotation, expand=True)
            if overview_only and picture.width > 1280:
                picture.thumbnail((1280, 1280))
            draw = ImageDraw.Draw(picture)
            labels = ['Frame %d | file PTS %.6f s' % (index, times[index])]
            if annotation:
                for trial in annotation.get('trials', []):
                    for event in ('hand_onset', 'game_onset', 'hand_stop', 'game_settled'):
                        if trial.get(event) == index:
                            labels.append('%s: %s' % (trial['label'], event))
                for window in annotation.get('stationary', []):
                    for point in window.get('points', []):
                        if point['frame'] == index:
                            for prefix, color in (('hand', 'yellow'), ('glove', 'cyan')):
                                x, y = point[prefix+'_x'], point[prefix+'_y']
                                draw.ellipse((x-5,y-5,x+5,y+5), outline=color, width=2)
            picture = ImageOps.expand(picture, border=(0,18*len(labels)+8,0,0), fill='black')
            draw = ImageDraw.Draw(picture)
            draw.multiline_text((4,4),'\n'.join(labels),fill='white',spacing=6)
            destination = args.output_dir / ('frame-%06d.png' % index)
            picture.save(destination, compress_level=1)
            saved.append(destination)
    build_contact_sheet(saved, args.output_dir/'contact-sheet.png')
    with (args.output_dir/'report.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
