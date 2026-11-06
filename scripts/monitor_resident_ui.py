"""Bounded read-only touch/presentation samples; does not inject input or reboot."""
from pathlib import Path
import argparse
import datetime
import json
import re
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--release', required=True, choices=['u81', 'u82', 'u83', 'u84'])
p.add_argument('--seconds', type=int, default=30)
p.add_argument('--interval', type=float, default=1)
a = p.parse_args()
assert 1 <= a.seconds <= 600 and 0.2 <= a.interval <= 10
dev = Path(__file__).resolve().parents[1]
root = dev.parents[1]
fastboot = root / 'outputs/MIX4-iOS16.5-touch-userland-r64-input-sampler/tools/fastboot.exe'
out = root / ('outputs/MIX4-UniXNU-desktop-' + a.release) / 'ui-monitor' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
out.mkdir(parents=True)
names = ['touch', 'hid', 'present'] + (['surface'] if a.release in ('u82', 'u83', 'u84') else [])
samples = []
start = time.monotonic()
while True:
    sample = {'elapsed_seconds': round(time.monotonic() - start, 3), 'counters': {}}
    for name in names:
        r = subprocess.run([str(fastboot), '-s', 'odin-unixnu-u64', 'oem', name + '-stats'],
                           capture_output=True, timeout=5)
        text = (r.stdout + r.stderr).decode(errors='replace')
        rows = re.findall(re.escape(name) + r'\[(\d+)\]=([0-9a-fA-F,]+)', text)
        assert not r.returncode and [int(i) for i, _ in rows] == [0, 4, 8, 12], text
        values = [int(v, 16) for _, row in rows for v in row.split(',')]
        assert len(values) == 16
        sample['counters'][name] = values
    samples.append(sample)
    with (out / 'samples.jsonl').open('a') as f:
        f.write(json.dumps(sample) + '\n')
    if time.monotonic() - start >= a.seconds:
        break
    time.sleep(min(a.interval, max(0, a.seconds - (time.monotonic() - start))))

first, last = samples[0]['counters'], samples[-1]['counters']
delta = lambda name, index: (last[name][index] - first[name][index]) & 0xffffffff
report = {
    'release': a.release, 'samples': len(samples), 'elapsed_seconds': samples[-1]['elapsed_seconds'],
    'partition_writes': False, 'input_injected': False, 'rebooted': False,
    'touch_polls': delta('touch', 2), 'touch_reports_accepted': delta('touch', 10),
    'touch_reports_rejected': delta('touch', 11),
    'frames_started': delta('present', 0), 'frames_copied': delta('present', 1),
    'map_prepare_errors': delta('present', 12), 'source_map_errors': delta('present', 13),
    'note': 'Counters alone do not establish UI responsiveness; correlate with actual interaction.'
}
if 'surface' in names:
    report['surface_deltas'] = dict(zip(
        ['validated_requests', 'surfaces', 'wrong_class', 'backed_surfaces', 'accepted', 'rejected',
         'kicks', 'copied', 'retired', 'map_failures', 'activation_refused', 'outside_gate',
         'ready_mismatch', 'reserved13', 'reserved14', 'reserved15'],
        [delta('surface', i) for i in range(16)]))
(out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
print(out)
