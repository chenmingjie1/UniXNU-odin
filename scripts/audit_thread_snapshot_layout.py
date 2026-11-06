"""Derive the pinned upstream observer's layout from our actual compiler objects.

Host only. The native accessors must match the prelinked replay kernel byte for
byte before their DWARF layouts are accepted. No target-device operations.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import argparse
from build_odin_display_owner import SSH, SCP

DEV = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-tag', default='u31')
parser.add_argument('--output-tag', default='u46')
args = parser.parse_args()
assert args.build_tag.isalnum() and args.output_tag.isalnum()
OUT = DEV / ('build/thread-snapshot-' + args.output_tag)
OUT.mkdir(exist_ok=True)
if args.output_tag != 'u46':
    assert not (OUT / 'plan.json').exists(), 'Preserve existing observer plan'
BASE = '/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
requests = {
    'thread.o': ('osfmk', ('thread', 'machine_thread', 'thread_ro')),
    'task.o': ('osfmk', ('task', '_vm_map')),
    'kern_proc.o': ('bsd', ('proc', 'proc_ro')),
    'vm_shared_region.o': ('osfmk', ('vm_shared_region',)),
    'pmap.o': ('osfmk', ('pmap', 'page_table_attr')),
}
remote = '''import subprocess,json,hashlib
from pathlib import Path
base=Path(%r)
requests=%r
out={}
for name,(part,structures) in requests.items():
 p=base/part/'DEVELOPMENT'/name
 out[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'structures':{}}
 for structure in structures:
  out[name]['structures'][structure]=subprocess.check_output(['llvm-dwarfdump','--name='+structure,'--show-children',str(p)],text=True)
out['accessor']=subprocess.check_output(['llvm-objdump','--disassemble','--disassemble-symbols=_proc_name_address',str(base/'bsd/DEVELOPMENT/kern_proc.o')],text=True)
print(json.dumps(out))
''' % (BASE, requests)
result = subprocess.run([*SSH, 'python3 -'], input=remote, capture_output=True, text=True, check=True)
raw = json.loads(result.stdout)
(OUT / 'compiler-layout-source.json').write_text(json.dumps(raw, indent=2) + '\n')
if args.output_tag != 'u46':
    for name, (part, _) in requests.items():
        subprocess.run([*SCP, 'odin@127.0.0.1:' + BASE + '/' + part + '/DEVELOPMENT/' + name,
                        str(OUT / name)], check=True)
    expected = {name: raw[name]['sha256'] for name in requests}
    (OUT / 'objects.json').write_text(json.dumps(expected, indent=2) + '\n')
else:
    expected = json.loads((OUT / 'objects.json').read_text())
for name in requests:
    assert raw[name]['sha256'] == expected[name] == hashlib.sha256((OUT / name).read_bytes()).hexdigest()


def member(obj, structure, name):
    text = raw[obj]['structures'][structure]
    # Do not allow a missing member to match a later member's location.
    blocks = re.split(r'\n0x[0-9a-f]+:', text)
    hits = [int(m[1], 16) for block in blocks
            if block.startswith('   DW_TAG_member\n')
            and re.search(r'DW_AT_name\s+\("' + re.escape(name) + r'"\)', block)
            and (m := re.search(r'DW_AT_data_member_location\s+\((0x[0-9a-f]+)\)', block))]
    assert len(hits) == 1, (obj, structure, name, hits)
    return hits[0]


def macho(path):
    data = path.read_bytes()
    pos = 32
    segments = []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == 25:
            _, va, _, off, length = struct.unpack_from('<16s4Q', data, pos + 8)
            segments.append((va, off, length))
        if cmd == 2:
            symoff, count, stroff, _ = struct.unpack_from('<4I', data, pos + 8)
        pos += size
    symbols = {}
    for index in range(count):
        name, kind, _, _, va = struct.unpack_from('<IBBHQ', data, symoff + 16 * index)
        if kind & 14 == 14:
            start = stroff + name
            symbols[data[start:data.index(0, start)].decode()] = va

    def read(va, length):
        matches = [data[off + va - base:off + va - base + length]
                   for base, off, size in segments if base <= va and va + length <= base + size]
        assert len(matches) == 1
        return matches[0]
    return data, symbols, read


native, ns, nr = macho(DEV / ('build/display-owner-' + args.build_tag) / 'native-real-iig.macho')
kernel, ks, kr = macho(DEV / ('build/display-owner-' + args.build_tag) / 'kernel.prelinked.experimental.macho')
if args.build_tag == 'u31':
    assert hashlib.sha256(kernel).hexdigest() == 'ab67534e74266878a8f13a58c533885c82217a5b9f02f85df0f77fb33dae03a4'
checks = []
for symbol in ('_proc_name_address', '_get_task_map', '_get_task_pmap', '_get_threadtask', '_thread_tid'):
    if symbol not in ns or symbol not in ks:
        continue
    code = nr(ns[symbol], 16)
    assert code == kr(ks[symbol], 16), symbol
    checks.append(dict(symbol=symbol, bytes=16, sha256=hashlib.sha256(code).hexdigest()))
assert len(checks) >= 3
code = kr(ks['_proc_name_address'], 8)
word = struct.unpack_from('<I', code)[0]
assert word & 0xffc003ff == 0x91000000  # add x0,x0,#imm
comm = (word >> 10) & 4095
assert struct.unpack_from('<I', code, 4)[0] == 0xd65f03c0
assert '_native_pt_attr' in ks and '_allproc' in ks
assert '"pmap_pt_attr"' not in raw['pmap.o']['structures']['pmap']
process = dict(
    thread_ro=member('thread.o', 'thread', 't_tro'),
    thread_user_state=member('thread.o', 'thread', 'machine') + member('thread.o', 'machine_thread', 'upcb'),
    ro_owner=member('thread.o', 'thread_ro', 'tro_owner'),
    ro_proc=member('thread.o', 'thread_ro', 'tro_proc'),
    ro_task=member('thread.o', 'thread_ro', 'tro_task'),
    pid=member('kern_proc.o', 'proc', 'p_pid'), comm=comm,
    list=member('kern_proc.o', 'proc', 'p_list'),
    stat=member('kern_proc.o', 'proc', 'p_stat'),
    task_region=member('task.o', 'task', 'shared_region'),
    region_slide=member('vm_shared_region.o', 'vm_shared_region', 'sr_slide'))
snapshot = dict(
    proc_ro=member('kern_proc.o', 'proc', 'p_proc_ro'),
    proc_ro_owner=member('kern_proc.o', 'proc_ro', 'pr_proc'),
    proc_ro_task=member('kern_proc.o', 'proc_ro', 'pr_task'),
    task_threads=member('task.o', 'task', 'threads'),
    task_thread_count=member('task.o', 'task', 'thread_count'),
    thread_link=member('thread.o', 'thread', 'task_threads'),
    thread_id=member('thread.o', 'thread', 'thread_id'),
    continuation=member('thread.o', 'thread', 'continuation'),
    wait_event=member('thread.o', 'thread', 'wait_event'),
    thread_state=member('thread.o', 'thread', 'state'),
    task_map=member('task.o', 'task', 'map'),
    map_pmap=member('task.o', '_vm_map', 'pmap'),
    pmap_ttep=member('pmap.o', 'pmap', 'ttep'),
    attr_root=member('pmap.o', 'page_table_attr', 'pta_root_level'),
    attr_shift=member('pmap.o', 'page_table_attr', 'pta_page_shift'))
plan = dict(process_layout=process, thread_snapshot_layout=snapshot,
    thread_snapshot_native_pt_attr=ks['_native_pt_attr'], allproc=ks['_allproc'],
    native_sha256=hashlib.sha256(native).hexdigest(), kernel_sha256=hashlib.sha256(kernel).hexdigest(),
    object_sha256=expected, linked_accessors=checks,
    upstream_commit='82b847c4ac3f68a57024b3082ffa3a03442defd9',
    device_commands_executed=False, read_only=True)
upstream = DEV / 'research/github-display-20261104/UniXNU--UniXNU/source/UniXNU-82b847c4ac3f68a57024b3082ffa3a03442defd9/scripts/qemu-entry'
plan['upstream_files'] = {name: hashlib.sha256((upstream / name).read_bytes()).hexdigest()
                          for name in ('thread_snapshot.py', 'gdb_packets.py')}
(OUT / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
print(json.dumps(plan, indent=2))
