"""Summarize measured input/frame progress without assuming an idle wait is a deadlock."""
from pathlib import Path
from collections import Counter, defaultdict
import argparse
import json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    samples = [json.loads(line) for line in (a.directory / 'samples.jsonl').read_text().splitlines()]
    assert samples and all('threads' in s and 'counters' in s for s in samples)
    transitions = []
    waits = defaultdict(Counter)
    for s in samples:
        seen = set()
        for t in s['threads']:
            if t['name'] in seen:
                continue
            seen.add(t['name'])
            waits[t['name']][(t['tid'], t['state'], t['continuation_symbol'], t['wait_event'])] += 1
    for before, after in zip(samples, samples[1:]):
        delta = lambda group, index: (after['counters'][group][index] - before['counters'][group][index]) & 0xffffffff
        if delta('touch', 10):
            frame_count = delta('present', 1)
            transitions.append(dict(
                from_sequence=before['sequence'], to_sequence=after['sequence'],
                elapsed_seconds=round(after['elapsed_seconds'] - before['elapsed_seconds'], 3),
                touch_reports=delta('touch', 10), frames=frame_count,
                average_copy_us=round(delta('present', 15) / frame_count, 1) if frame_count else None,
                surface_requests=delta('surface', 0), surface_rejections=delta('surface', 5),
                copied_bytes_last=after['counters']['present'][11],
                copy_us_last=after['counters']['present'][2],
                total_us_last=after['counters']['present'][8]))
    frame_count = (samples[-1]['counters']['present'][1] - samples[0]['counters']['present'][1]) & 0xffffffff
    copy_us = (samples[-1]['counters']['present'][15] - samples[0]['counters']['present'][15]) & 0xffffffff
    report = dict(
        samples=len(samples), elapsed_seconds=samples[-1]['elapsed_seconds'],
        frames_copied=frame_count, copy_microseconds_accumulated=copy_us,
        average_copy_us=round(copy_us / frame_count, 1) if frame_count else None,
        first_sequence=samples[0]['sequence'], last_sequence=samples[-1]['sequence'],
        user_action_intervals=transitions,
        first_thread_boundaries={name: [dict(tid=k[0], state=k[1], continuation=k[2], wait_event=hex(k[3]), samples=n)
            for k, n in counts.most_common()] for name, counts in waits.items()},
        limits=[
            'A saved user PC is the last boundary; it is not a complete userspace stack.',
            'A normal Mach receive, semaphore or workqueue wait alone is not evidence of a deadlock.',
            'No shared-cache slide is assumed.',
            'At most32 threads per process and96 total are captured; other threads may be omitted.',
            'Per-frame last timings can repeat between samples; these are not frame-weighted averages.',
            'Touch/frame counters require physical observation to qualify usable input or a permanent freeze.'])
    policies = []
    for s in samples:
        v = s['counters'].get('policy')
        if v is None:
            continue
        policies.append(dict(elapsed_seconds=s['elapsed_seconds'],
            version=v[0], heartbeat=v[1], command_seen=v[2],
            app_available=bool(v[3] & 1), backlight_available=bool(v[3] & 2),
            screen_on=v[4], digitizer_disabled=v[5], idle_timer_disabled=v[6],
            screen_dim=v[7], locked=v[8], native_reset_calls=v[9],
            screen_on_after=v[10], command_sysctl_result=v[11],
            idle_disabled_after=v[12] if v[13] == 2 else None,
            policy_mode=v[13],
            global_ui_idle_disabled=v[12] if v[13] == 4 else None,
            global_ui_assertions_present=v[14] if v[13] == 4 else None,
            global_ui_assertions_prevented=v[15] if v[13] == 4 else None,
            frames_copied=s['counters']['present'][1],
            hid_reports=s['counters']['hid'][5]))
    if policies:
        report['ui_policy_timeline'] = policies
        report['limits'] += [
            'Policy getter value 255 means unavailable, not true.',
            'Policy heartbeat runs on the SpringBoard main queue; a stalled heartbeat may mean this queue cannot run.',
            'A firmware command acknowledgement alone does not prove userspace observed it or native wake restored physical input.']
    out = a.directory / 'analysis.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(out)
    print('Action intervals:', len(transitions), 'with frames:', sum(t['frames'] > 0 for t in transitions))
    for t in transitions:
        print(t)


if __name__ == '__main__':
    main()
