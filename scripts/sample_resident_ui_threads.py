"""Read fixed UI thread samples and resolve kernel continuations in the exact image.

No input injection, process manipulation, device writes or reboots.
Userspace PCs remain raw: a shared-cache slide must be measured, not guessed.
"""
from pathlib import Path
import argparse
import bisect
import datetime
import json
import re
import struct
import subprocess
import time


def kernel_symbols(path):
    raw = path.read_bytes()
    assert struct.unpack_from('<I', raw)[0] == 0xfeedfacf
    pos = 32
    syms = []
    for _ in range(struct.unpack_from('<I', raw, 16)[0]):
        kind, size = struct.unpack_from('<II', raw, pos)
        if kind == 2:
            offset, count, strings, length = struct.unpack_from('<4I', raw, pos + 8)
            for i in range(count):
                name, typ, section, desc, address = struct.unpack_from('<IBBHQ', raw, offset + i * 16)
                if typ & 0xe == 0xe and address:
                    start = strings + name
                    end = raw.index(b'\0', start, strings + length)
                    syms.append((address, raw[start:end].decode(errors='replace')))
        pos += size
    return sorted(set(syms))


def parse_sample(text):
    h = re.search(r'ui sequence=([0-9a-f]+) count=(\d+) ticks=([0-9a-f]+)', text, re.I)
    if not h:
        raise ValueError('No completed UI sample: ' + text)
    count = int(h[2])
    if not 0 <= count <= 96:
        raise ValueError('Invalid UI thread count')
    rows = {}
    for prefix, fields in [('ui', ['process', 'tid', 'state']),
                           ('uw', ['wait_event', 'continuation']),
                           ('up', ['user_pc', 'user_lr']), ('us', ['user_sp', 'user_x0'])]:
        matches = re.findall(prefix + r'\[(\d+)\]=([0-9a-f,]+)', text, re.I)
        if len(matches) != count or [int(i) for i, _ in matches] != list(range(count)):
            raise ValueError('Incomplete or duplicate ' + prefix + ' rows')
        for index, values in matches:
            nums = [int(v, 16) for v in values.split(',')]
            if len(nums) != len(fields):
                raise ValueError('Invalid ' + prefix + ' row width')
            rows.setdefault(int(index), {}).update(zip(fields, nums))
    return dict(sequence=int(h[1], 16), ticks=int(h[3], 16), threads=list(rows.values()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release', choices=['u83', 'u84', 'u85', 'u86', 'u87', 'u88', 'u89'], default='u83')
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--interval', type=float, default=2)
    p.add_argument('--wait-sampler', type=int, default=0, help='Bounded startup wait for the first published bank')
    a = p.parse_args()
    assert 0 <= a.seconds <= 600 and 1 <= a.interval <= 30
    assert 0 <= a.wait_sampler <= 300
    dev = Path(__file__).resolve().parents[1]
    root = dev.parents[1]
    kernel = dev / ('build/device-desktop-' + a.release + '/esp/EFI/UniXNU/Payloads/kernel.macho')
    syms = kernel_symbols(kernel)
    addresses = [v[0] for v in syms]
    fastboot = root / 'outputs/MIX4-iOS16.5-touch-userland-r64-input-sampler/tools/fastboot.exe'
    out = root / ('outputs/MIX4-UniXNU-desktop-' + a.release) / 'ui-threads' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out.mkdir(parents=True)
    import hashlib
    (out / 'scope.json').write_text(json.dumps(dict(
        kernel=str(kernel), kernel_sha256=hashlib.sha256(kernel.read_bytes()).hexdigest(),
        approximate_per_thread=True, userspace_slide_measured=False,
        no_process_manipulation=True, no_partition_writes=True), indent=2))
    start = time.monotonic()
    startup_deadline = start + a.wait_sampler
    iteration = 0
    while True:
        r = subprocess.run([str(fastboot), '-s', 'odin-unixnu-u64', 'oem', 'ui-threads'], capture_output=True, timeout=10)
        text = (r.stdout + r.stderr).decode(errors='replace')
        (out / f'{iteration:04d}.txt').write_text(text)
        if r.returncode and iteration == 0 and time.monotonic() < startup_deadline and (
                'UI sampler has no completed sample' in text):
            time.sleep(1)
            start = time.monotonic()
            continue
        assert r.returncode == 0, text
        sample = parse_sample(text)
        sample['elapsed_seconds'] = round(time.monotonic() - start, 3)
        sample['counters'] = {}
        for name in ('touch', 'hid', 'present', 'surface', *(['policy'] if a.release in ('u85', 'u86', 'u87', 'u88', 'u89') else [])):
            r = subprocess.run([str(fastboot), '-s', 'odin-unixnu-u64', 'oem', 'ui-policy' if name == 'policy' else name + '-stats'],
                               capture_output=True, timeout=5)
            raw_text = (r.stdout + r.stderr).decode(errors='replace')
            (out / f'{iteration:04d}-{name}.txt').write_text(raw_text)
            matches = re.findall(name + r'\[(\d+)\]=([0-9a-f,]+)', raw_text, re.I)
            assert not r.returncode and [int(i) for i, _ in matches] == [0, 4, 8, 12], raw_text
            values = [int(v, 16) for _, row in matches for v in row.split(',')]
            assert len(values) == 16, raw_text
            sample['counters'][name] = values
        for row in sample['threads']:
            process = row.pop('process')
            row['pid'] = process & 0xffffffff
            row['name'] = {1: 'SpringBoard', 2: 'backboardd', 3: 'Preferences'}.get(process >> 32, 'unknown')
            address = row['continuation']
            index = bisect.bisect_right(addresses, address) - 1
            if index >= 0 and address - addresses[index] < 0x10000:
                row['continuation_symbol'] = syms[index][1] + '+0x%x' % (address - addresses[index])
            else:
                row['continuation_symbol'] = None
        with (out / 'samples.jsonl').open('a') as f:
            f.write(json.dumps(sample) + '\n')
        print('sample', sample['sequence'], 'threads', len(sample['threads']), flush=True)
        iteration += 1
        if time.monotonic() - start >= a.seconds:
            break
        time.sleep(min(a.interval, max(0, a.seconds - (time.monotonic() - start))))
    print(out, flush=True)


if __name__ == '__main__':
    main()
