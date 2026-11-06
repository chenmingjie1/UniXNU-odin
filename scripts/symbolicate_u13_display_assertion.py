"""Qualify the observed EL0 BRK against the exact iOS16 cache and decode its assertion."""
from pathlib import Path
import hashlib
import json
import mmap
import re
import struct
import sys

root = Path(__file__).resolve().parents[3]
run = root / 'work/UniXNU-odin/build/qemu-early-entry-u13cryptex'
out = root / 'outputs/MIX4-UniXNU-host-u12'
sys.path.insert(0, str(root / 'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache, DEFAULT

trace_bytes = (run / 'trace.log').read_bytes()
trace = trace_bytes.decode('utf8')
exception = re.search(r'Taking exception 7 \[Breakpoint\].*?from EL0 to EL1.*?'
                      r'ESR 0x3c/0xf2000000.*?ELR (0x[0-9a-f]+)', trace, re.S)
assert exception
pc = int(exception[1], 16)
previous = re.search(rf'^{hex(pc-4)}:  ([0-9a-f]{{8}})  bl ', trace, re.M)
assert previous and f'{hex(pc)}:  d4200000  brk' in trace
needle = struct.pack('<II', int(previous[1], 16), 0xd4200000)
hits = []
for path in sorted(DEFAULT.parent.glob(DEFAULT.name + '*')):
    with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:16] != b'dyld_v1   arm64\0':
            continue
        off, count = struct.unpack_from('<II', data, 16)
        mappings = [struct.unpack_from('<3Q2I', data, off+i*32) for i in range(count)]
        position = data.find(needle)
        while position >= 0:
            for start, size, fileoff, _, prot in mappings:
                if prot & 4 and fileoff <= position and position+8 <= fileoff+size:
                    hits.append({'file': path.name, 'offset': position,
                                 'unslid_pc': start+position-fileoff+4})
            position = data.find(needle, position+1)
assert len(hits) == 1
slide = pc-hits[0]['unslid_pc']
assert slide >= 0 and slide % 4096 == 0
cache = Cache(DEFAULT)
# Independently qualify the observed logger shim's three instructions.
anchor = re.search(r'^(0x[0-9a-f]+):  f0279d68  adrp.*?\n'
                   r'0x[0-9a-f]+:  f9048100  str.*?\n'
                   r'0x[0-9a-f]+:  d65f03c0  ret', trace, re.M)
assert anchor
anchor_pc = int(anchor[1], 16)
assert cache.read(anchor_pc-slide, 12) == bytes.fromhex('689d27f0008104f9c0035fd6')
unslid = hits[0]['unslid_pc']
resolved = cache.resolve(unslid)
assert resolved['image'].endswith('/FrontBoardServices.framework/FrontBoardServices')
reference = unslid-0x48
adrp, add = struct.unpack('<II', cache.read(reference, 8))
assert adrp & 0x9f00001f == 0x90000002
assert add & 0xffc003ff == 0x91000042
immediate = ((adrp >> 29) & 3) | (((adrp >> 5) & 0x7ffff) << 2)
if immediate & (1 << 20):
    immediate -= 1 << 21
literal = (reference & ~4095) + (immediate << 12) + ((add >> 10) & 4095)
pointer, length = struct.unpack_from('<QQ', cache.read(literal, 32), 16)
assert 0 < length <= 256
slide_info = []
for path in sorted(DEFAULT.parent.glob(DEFAULT.name + '*')):
    with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:16] != b'dyld_v1   arm64\0':
            continue
        off, count = struct.unpack_from('<II', data, 312)
        assert count <= 64 and off+count*56 <= len(data)
        for index in range(count):
            mapping = struct.unpack_from('<6Q2I', data, off+index*56)
            if mapping[0] <= literal < mapping[0]+mapping[1]:
                info = data[mapping[3]:mapping[3]+40]
                assert struct.unpack_from('<I', info)[0] == 2
                mask, base = struct.unpack_from('<QQ', info, 24)
                slide_info.append((mask, base, path.name))
assert len(slide_info) == 1
mask, base, data_file = slide_info[0]
string_address = (pointer & (~mask & ((1 << 64)-1))) + base
message = cache.read(string_address, length).decode('ascii')
assert message == 'failed to find the main CADisplay'
record = {
    'scope': 'Host QEMU exception and exact local cache; no phone operation',
    'kernel_sha256': json.loads((run/'verification.json').read_text())['kernel_sha256'],
    'trace_sha256': hashlib.sha256(trace_bytes).hexdigest(),
    'actual_exception': 'EL0 BRK #0 / EXC_BREAKPOINT / SIGTRAP',
    'runtime_pc': hex(pc), 'unique_instruction_match': hits[0],
    'independent_instruction_anchor': hex(anchor_pc), 'cache_slide': hex(slide),
    'resolved': resolved, 'static_assertion': message,
    'cfstring_address': hex(literal), 'slide_info_file': data_file,
    'runtime_assertion_text_captured': False,
    'original_files_modified': False, 'desktop_verified': False,
    'remaining': 'Publish a version-qualified native display provider before claiming a desktop',
}
cache.close()
(out/'u13-display-assertion.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record, indent=2))
