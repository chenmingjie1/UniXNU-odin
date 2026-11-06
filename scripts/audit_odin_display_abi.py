"""Discover display dispatch from the exact iOS 16.5 original family.

Computer-only static evidence. Nothing here publishes a service or qualifies
method prototypes, runtime object layout, or hardware scanout.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / 'work/UniXNU-odin'
sys.path.insert(0, str(ROOT / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

KERNEL = DEV / 'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho'
PLAN = KERNEL.with_name('prelink-emission-report.json')
OUT = DEV / 'build/display-analysis-ios16'
OUT.mkdir(exist_ok=True)
blob = KERNEL.read_bytes()
plan = json.loads(PLAN.read_text())
assert hashlib.sha256(blob).hexdigest() == plan['candidate_sha256']
assert plan['original_sha256'] == 'e6fa75598f47b5a9460a60913e2ac8e4cd6cd60eb475bb31da65b68ffbcfdad5'
image = np.macho(blob)
symbols = np.exports(blob, image)
names = {name: va for va, group in symbols.items() for name in group}
family = 'com.apple.iokit.IOMobileGraphicsFamily'
extents = {e['segment']: e for e in plan['extents'] if e['module'] == family}


def read(va, length):
    offset = np.backed_offset(image['segments'], va, length, len(blob))
    return blob[offset:offset+length]


def addr_pair(pc, a, b):
    """An ADRP followed by ADD immediate using the same source register."""
    if a & 0x9f000000 != 0x90000000 or b & 0xffc00000 != 0x91000000:
        return None
    if a & 31 != (b >> 5) & 31:
        return None
    immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    return (pc & ~4095) + (immediate << 12) + (b >> 10 & 4095), b & 31


text = extents['__TEXT_EXEC']
code = read(text['va'], text['size'])
assert hashlib.sha256(code).hexdigest() == plan['original_executable_sha256'][family]
const = extents['__DATA_CONST']
data = read(const['va'], const['size'])
cstrings = extents['__TEXT']
string_blob = read(cstrings['va'], cstrings['size'])
class_names = {}
for name in (b'IOMobileFramebuffer', b'IOMobileFramebufferService',
             b'IOMobileFramebufferLegacy', b'IOMobileFramebufferUserClient'):
    needle = b'\0' + name + b'\0'
    found = []
    position = string_blob.find(needle)
    while position >= 0:
        found.append(cstrings['va'] + position + 1)
        position = string_blob.find(needle, position+1)
    assert len(found) == 1, (name, found)
    class_names[found[0]] = name.decode()

references = []
for offset in range(0, len(code)-8, 4):
    a, b = struct.unpack_from('<II', code, offset)
    pair = addr_pair(text['va']+offset, a, b)
    if pair and pair[0] in class_names:
        # Keep the unmodified instruction window for independent disassembly.
        start, stop = max(0, offset-24), min(len(code), offset+80)
        references.append(dict(name=class_names[pair[0]], pc=hex(text['va']+offset),
            string=hex(pair[0]), argument_register=pair[1],
            window_start=hex(text['va']+start), window_hex=code[start:stop].hex()))

# Match five real source-kernel OSObject entries; do not infer a table from
# guessed iPadOS addresses, table length or class size.
prefix_names = ['__ZNK8OSObject7releaseEi', '__ZNK8OSObject14getRetainCountEv',
                '__ZNK8OSObject6retainEv', '__ZNK8OSObject7releaseEv',
                '__ZNK8OSObject9serializeEP11OSSerialize']
prefix = struct.pack('<5Q', *(names[name] for name in prefix_names))
tables = []
position = data.find(prefix)
while position >= 0:
    start = position-32  # null header, then two destructors, then slot 2
    if start >= 0 and start % 8 == 0 and data[start:start+16] == bytes(16):
        methods = []
        cursor = start+16
        while cursor+8 <= len(data):
            value = struct.unpack_from('<Q', data, cursor)[0]
            if not value:
                break
            # Dispatch entries must point to actual executable extents.
            executable = any(s['va'] <= value < s['va']+s['size'] and s.get('initprot', 0) & 4
                             for s in image['segments'])
            # macho's segment records may omit protections; backing alone is
            # insufficient, so the known text range/kernel export is required.
            executable = executable or text['va'] <= value < text['va']+text['size'] or value in symbols
            if not executable:
                break
            methods.append(value)
            cursor += 8
        if len(methods) >= 168:
            getter = read(methods[7], 24)
            meta = None
            # This original release retains an O0 stack prologue, unlike the
            # optimized iPadOS reference. Match the actual return sequence.
            for delta in (0, 8):
                a, b = struct.unpack_from('<II', getter, delta)
                pair = addr_pair(methods[7]+delta, a, b)
                if pair and pair[1] == 0 and struct.unpack_from('<I', getter, 20)[0] == 0xd65f03c0:
                    meta = pair[0]
            tables.append(dict(vtable=hex(const['va']+start), vptr=hex(const['va']+start+16),
                entries=len(methods), metaclass=hex(meta) if meta else None,
                abstract_slots=[i for i, value in enumerate(methods) if value == names['___cxa_pure_virtual']],
                methods=[dict(slot=i, address=hex(value), kernel_names=symbols.get(value, []))
                         for i, value in enumerate(methods)]))
    position = data.find(prefix, position+1)

def branch(pc, word):
    imm = word & 0x3ffffff
    if imm & 0x2000000:
        imm -= 0x4000000
    return pc + imm * 4


def function_start(pc):
    # All constructors in this particular original build have a retained
    # stack-frame prologue. Do not assume a length from the other OS build.
    for back in range(4, 100, 4):
        word = struct.unpack('<I', read(pc-back, 4))[0]
        if word & 0xffc003ff == 0xd10003ff or word == 0xa9bf7bfd:
            return pc-back
        if word == 0xd65f03c0:
            break
    return None


for reference in references:
    pc = int(reference['pc'], 16)
    a, b, size, call = struct.unpack('<4I', read(pc+8, 16))
    pair = addr_pair(pc+8, a, b)
    if pair:
        parent = pair[0]
    else:
        assert a & 0x9f00001f == 0x90000002 and b & 0xffc003ff == 0xf9400042
        # Parent imported from the actual native source-kernel GOT.
        immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
        if immediate & 0x100000:
            immediate -= 0x200000
        slot = ((pc+8) & ~4095) + immediate*4096 + ((b >> 10) & 4095)*8
        parent = struct.unpack('<Q', read(slot, 8))[0]
    assert size & 0xffe0001f == 0x52800003 and call & 0xfc000000 == 0x94000000
    reference.update(parent_metaclass=hex(parent), instance_bytes=(size >> 5) & 65535,
        metaclass_constructor=hex(function_start(pc)))
    constructor = int(reference['metaclass_constructor'], 16)
    callers = []
    targets = {constructor}
    visited = set()
    for depth in range(3):
        next_targets = set()
        for off in range(0, len(code)-4, 4):
            w = struct.unpack_from('<I', code, off)[0]
            callpc = text['va']+off
            if w & 0x7c000000 != 0x14000000 or branch(callpc, w) not in targets:
                continue
            # C1 forwards to C2 through a retained stack wrapper in this build.
            for back in (8, 12, 16):
                aa, bb = struct.unpack('<II', read(callpc-back, 8))
                argument = addr_pair(callpc-back, aa, bb)
                if argument and argument[1] == 0:
                    callers.append(dict(call_pc=hex(callpc), metaclass=hex(argument[0]), wrapper_depth=depth))
                    break
            else:
                start = function_start(callpc)
                if start is not None:
                    next_targets.add(start)
        visited.update(targets)
        targets = next_targets-visited
        if not targets:
            break
    reference['registration_calls'] = callers
    assert len({c['metaclass'] for c in callers}) == 1, reference
    meta = callers[0]['metaclass']
    matches = [t for t in tables if t['metaclass'] == meta]
    assert len(matches) == 1, reference
    matches[0].update(name=reference['name'], instance_bytes=reference['instance_bytes'],
                      parent_metaclass=reference['parent_metaclass'])

for table in tables:
    vptr = int(table['vptr'], 16)
    constructors = []
    for off in range(0, len(code)-12, 4):
        aa, bb, cc = struct.unpack_from('<III', code, off)
        pair = addr_pair(text['va']+off, aa, bb)
        if pair and pair[0]+16 == vptr and pair[1] == 8 and cc == 0x91004108:
            start = function_start(text['va']+off)
            if start:
                constructors.append(hex(start))
    table['constructor_candidates'] = constructors

classes = {t['name']: t for t in tables if 'name' in t}
base, service, legacy = (classes[name] for name in ('IOMobileFramebuffer',
    'IOMobileFramebufferService', 'IOMobileFramebufferLegacy'))
assert [i for i, (a, b) in enumerate(zip(base['methods'], service['methods']))
        if a['address'] != b['address']] == [0, 1, 7]
assert legacy['parent_metaclass'] == service['metaclass']
assert service['parent_metaclass'] == base['metaclass']
assert base['parent_metaclass'] == hex(names['__ZN9IOService10gMetaClassE'])
assert (base['entries'], service['entries'], legacy['entries']) == (252, 252, 338)
assert (base['instance_bytes'], service['instance_bytes'], legacy['instance_bytes']) == (0x90, 0x90, 0x1660)
assert legacy['abstract_slots'] == [211, 212, 242, 243, 292, 293, 321, 322, 329]
for table in (base, service, legacy):
    assert len(table['constructor_candidates']) == 1
    constructor = int(table['constructor_candidates'][0], 16)
    # The protected constructor ends at its first RET; the following D2
    # destructor forwards to the actual parent's D2. Complete destructors are
    # deliberate BRK traps for these original abstract classes.
    words = struct.unpack('<24I', read(constructor, 96))
    end = words.index(0xd65f03c0)
    calls = [(constructor+i*4, w) for i, w in enumerate(words[:end]) if w & 0xfc000000 == 0x94000000]
    assert len(calls) == 1
    table['protected_constructor'] = hex(constructor)
    table['parent_constructor'] = hex(branch(*calls[0]))
    table['base_destructor'] = hex(constructor+(end+1)*4)
    d2 = int(table['base_destructor'], 16)
    dwords = struct.unpack('<20I', read(d2, 80))
    dend = dwords.index(0xd65f03c0)
    dcalls = [(d2+i*4, w) for i, w in enumerate(dwords[:dend]) if w & 0xfc000000 == 0x94000000]
    assert len(dcalls) == 1
    table['parent_destructor'] = hex(branch(*dcalls[0]))
assert legacy['parent_constructor'] == service['protected_constructor']
assert service['parent_constructor'] == base['protected_constructor']
assert legacy['parent_destructor'] == service['base_destructor']
# The trivial Framebuffer D2 is bypassed by this compiler: both its D2 and
# Service D2 call the same original native-import thunk for IOService D2.
assert service['parent_destructor'] == base['parent_destructor']


def thunk_target(address):
    a, b, c = struct.unpack('<3I', read(address, 12))
    assert a & 0x9f00001f == 0x90000010 and b & 0xffc003ff == 0xf9400210 and c == 0xd61f0200
    immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    at = (address & ~4095) + immediate*4096 + ((b >> 10) & 4095)*8
    return struct.unpack('<Q', read(at, 8))[0]


assert thunk_target(int(base['parent_constructor'], 16)) == names['__ZN9IOServiceC2EPK11OSMetaClass']
assert thunk_target(int(base['parent_destructor'], 16)) == names['__ZN9IOServiceD2Ev']

record = dict(target_os='iOS 16.5 / 20F66', candidate_sha256=plan['candidate_sha256'],
    original_sha256=plan['original_sha256'], original_family_text_sha256=hashlib.sha256(code).hexdigest(),
    class_name_references=references, dispatch_candidates=tables,
    static_only=True, prototypes_qualified=False, runtime_verified=False,
    device_commands_executed=False, desktop_verified=False)
(OUT / 'dispatch-discovery.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('dispatch_candidates', 'class_name_references')}, indent=2))
for table in tables:
    print(table.get('name', 'unidentified'), table['entries'], table.get('instance_bytes'),
          table['metaclass'], 'pure:', table['abstract_slots'] if len(table['abstract_slots']) < 16 else len(table['abstract_slots']))
