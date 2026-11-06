"""Symbolicate upstream UI snapshots with each task's actual shared-cache slide.

Saved user PCs describe the last boundary; they alone do not prove a wait cause.
"""
from pathlib import Path
from collections import Counter
import argparse
import bisect
import json
import struct
from inspect_cache_objc_refs import Cache, DEFAULT

DEV = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', required=True)
a = p.parse_args()
assert a.tag.isalnum()
run = DEV / ('build/qemu-early-entry-' + a.tag)
c = Cache(DEFAULT)


def resolve(value, slide):
    if value is None or slide is None:
        return None
    address = int(value, 16)
    original = address - slide
    if not any(lo <= original < hi for lo, hi, *_ in c.maps):
        return dict(runtime=hex(address), unresolved='Outside this task shared cache; standalone executable or dyld')
    return dict(runtime=hex(address), original=c.resolve(original))


fatals = []
fatal_path = run / 'user-fatal-live.jsonl'
if fatal_path.exists():
    for line in fatal_path.read_text().splitlines():
        row = json.loads(line)
        slide = row.get('process', {}).get('cache_slide')
        if 'registers' in row:
            row['resolved_pc'] = resolve(row['registers']['PC'], slide)
            row['resolved_lr'] = resolve(row['registers']['LR'], slide)
        for frame in row.get('frames', []):
            frame['resolved'] = resolve(frame['lr'], slide)
        fatals.append(row)
report = dict(scope='Host-only read-only snapshots; no device commands',
    saved_pc_is_not_proof_of_current_wait=True, device_commands_executed=False,
    fatal_count=len(fatals), fatal_process_counts=dict(Counter(
        row.get('process', {}).get('name', '<unresolved>') for row in fatals)),
    fatals=fatals)
snapshot_path = run / 'ui-thread-snapshot.json'
if snapshot_path.exists():
    snapshot = json.loads(snapshot_path.read_text())
    report['snapshot'] = snapshot
    plan = json.loads((run / 'ui-thread-plan.json').read_text())
    native = (DEV / 'build/display-owner-u31/kernel.prelinked.experimental.macho').read_bytes()
    import hashlib
    assert hashlib.sha256(native).hexdigest() == plan['kernel_sha256']
    pos = 32
    for _ in range(struct.unpack_from('<I', native, 16)[0]):
        cmd, size = struct.unpack_from('<II', native, pos)
        if cmd == 2:
            so, count, st, _ = struct.unpack_from('<4I', native, pos + 8)
        pos += size
    symbols = []
    for i in range(count):
        name, kind, _, _, address = struct.unpack_from('<IBBHQ', native, so + i * 16)
        if kind & 14 == 14:
            start = st + name
            symbols.append((address, native[start:native.index(0, start)].decode()))
    symbols.sort()
    addresses = [address for address, _ in symbols]

    def kernel_symbol(value):
        address = int(value, 16)
        index = bisect.bisect_right(addresses, address) - 1
        if index < 0 or address - symbols[index][0] >= 65536:
            return None
        base, name = symbols[index]
        return dict(symbol=name, offset=hex(address - base), exact=base == address)

    for row in snapshot.get('ui_thread_snapshots', {}).get('processes', []):
        for thread in row.get('threads', []):
            thread['resolved_continuation'] = kernel_symbol(thread['continuation'])
            for field in ('pc', 'lr'):
                thread['resolved_' + field] = resolve(thread.get('user_' + field), row.get('cache_slide'))
            for frame in thread.get('user_frames', []):
                frame['resolved'] = resolve(frame['lr'], row.get('cache_slide'))
c.close()
output = run / 'ui-thread-analysis.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('fatals', 'snapshot')}, indent=2))
for row in fatals[:4]:
    print(row.get('process'), row.get('strings', {}).get('X19', {}).get('text'), row.get('error'))
