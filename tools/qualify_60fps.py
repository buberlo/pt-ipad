#!/usr/bin/env python3
"""Qualify actual 60 Hz presentation windows; never infer gameplay or visual acceptance.

Window boundaries are presentation IDs within one driver segment, not log seconds.
The caller must associate these windows with foreground scene/image evidence.
"""
import argparse
import csv
import json
import math
from pathlib import Path
from summarize_present_trace import summarize, TraceError
from build_provenance import digest

SCENES = {'corridor', 'bathroom', 'mirror_flashlight', 'encounter', 'microphone'}


def statistics(intervals):
    values = sorted(intervals)
    seconds = sum(values) / 1e9
    def pct(fraction):
        return values[max(0, math.ceil(len(values) * fraction) - 1)] / 1e6 if values else None
    slow = sum(value > 25_000_000 for value in values)
    result = {'intervals': len(values), 'seconds': seconds, 'actual_fps': len(values) / seconds if seconds else 0,
              'p95_ms': pct(.95), 'p99_ms': pct(.99), 'max_ms': values[-1] / 1e6 if values else None,
              'over_25_ms': slow, 'over_25_fraction': slow / len(values) if values else 1,
              'over_100_ms': sum(value > 100_000_000 for value in values)}
    result['timing_passed'] = bool(values and result['actual_fps'] >= 59.9 and result['p95_ms'] <= 17.2 and
                                   result['p99_ms'] <= 17.2 and result['over_25_fraction'] <= .001)
    return result


def qualify(trace, windows):
    source_hash = digest(trace)
    validation = summarize(trace, target_fps=60, warmup_seconds=0)
    if windows.get('schema') != 1 or not isinstance(windows.get('windows'), list):
        raise ValueError('expected schema-1 windows specification')
    with Path(trace).open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if digest(trace) != source_hash:
        raise ValueError('presentation trace changed during qualification')
    indexed = {}
    for row in rows:
        key = (int(row['segment']), int(row['present_id']))
        if key in indexed:
            raise ValueError('ambiguous presentation identity')
        indexed[key] = row
    results = []
    names = set()
    for window in windows['windows']:
        name, role = window.get('name'), window.get('role')
        segment, first, last = (window.get(key) for key in ('segment', 'first_present_id', 'last_present_id'))
        if (not isinstance(name, str) or not name or name in names or role not in ('gameplay', 'tail', 'scene') or
                any(type(value) is not int or value < 0 for value in (segment, first, last)) or first >= last):
            raise ValueError('invalid or duplicate presentation window')
        names.add(name)
        if (segment, first) not in indexed or (segment, last) not in indexed:
            raise ValueError('window endpoints not present in the selected segment')
        if last - first > len(rows):
            raise ValueError('window contains missing presentations')
        selected = [indexed[(segment, pid)] for pid in range(first + 1, last + 1) if (segment, pid) in indexed]
        if len(selected) != last - first or any(int(row['unobserved_ids_before']) for row in selected):
            raise ValueError('window contains missing presentations')
        value = statistics([int(row['interval_ns']) for row in selected])
        required = 1200 if role == 'gameplay' else 300 if role == 'tail' else 120
        value.update(name=name, role=role, segment=segment, first_present_id=first, last_present_id=last,
                     duration_passed=value['seconds'] >= required)
        results.append(value)
    gameplay = [r for r in results if r['role'] == 'gameplay']
    tails = [r for r in results if r['role'] == 'tail']
    scenes = {r['name'] for r in results if r['role'] == 'scene'}
    coverage = len(gameplay) == 1 and len(tails) == 1 and SCENES <= scenes
    if coverage:
        game, tail = gameplay[0], tails[0]
        coverage = (tail['segment'] == game['segment'] and tail['last_present_id'] == game['last_present_id'] and
                    tail['first_present_id'] >= game['first_present_id'] and 300 <= tail['seconds'] <= 300.1)
        coverage = coverage and all(
            r['segment'] == game['segment'] and
            game['first_present_id'] <= r['first_present_id'] < r['last_present_id'] <= game['last_present_id']
            for r in results if r['role'] == 'scene')
    return {'schema': 1, 'trace_sha256': source_hash, 'windows': results,
            'timing_passed': bool(coverage and results and all(r['timing_passed'] and r['duration_passed'] for r in results)),
            'coverage_complete': coverage, 'accepted': False,
            'remaining_evidence': ['foreground and scene association', '1920x1080 internal render extent',
                'unchanged graphics and visual review', 'warmup and thermal/Low Power Mode evidence', 'source/build/device identity'],
            'trace_validation_discontinuity': validation['trace_discontinuity']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--windows', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        result = qualify(args.trace, json.loads(args.windows.read_text()))
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print('Timing gate passed; scene/visual/device acceptance remains separate.' if result['timing_passed'] else 'Timing gate incomplete or failed.')
        raise SystemExit(0 if result['timing_passed'] else 2)
    except (OSError, ValueError, TraceError) as error:
        p.exit(1, f'60 FPS qualification failed: {error}\n')
