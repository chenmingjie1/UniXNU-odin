"""Resolve the observed standalone trap and its original chained CFString.

Read-only analysis of u33; this does not patch an executable or skip migration.
"""
from pathlib import Path
import hashlib
import json
import struct

DEV = Path(__file__).resolve().parents[1]
binary = DEV / 'build/root-media/activation-service-audit-u33/usr/libexec/mobileactivationd'
blob = binary.read_bytes()
assert hashlib.sha256(blob).hexdigest() == '9e0745feaea7c0ee337e2dfb0cfc04e9ab063fcbb2f761bc5394fbd298d3015e'
analysis = json.loads((DEV / 'build/qemu-early-entry-u33activationresume/desktop-runtime-analysis.json').read_text())
trap = next(row for row in analysis['observed_el0_breakpoints'] if row['runtime_pc'] == '0x1007a7b7c')
needle = bytes.fromhex(trap['matched_instructions'])
offset = blob.find(needle)
assert offset >= 0 and blob.find(needle, offset + 1) == -1
base = 0x100000000
original_pc = base + offset + len(needle) - 4
assert original_pc == 0x1001bbb7c
slide = int(trap['runtime_pc'], 16) - original_pc
assert slide == 0x5ec000
assert struct.unpack_from('<I', blob, original_pc - base)[0] == 0xd4200020

segments = []
position = 32
fixups = None
for _ in range(struct.unpack_from('<I', blob, 16)[0]):
    command, size = struct.unpack_from('<II', blob, position)
    if command == 25:
        name, va, vs, fileoff, filesize = struct.unpack_from('<16s4Q', blob, position + 8)
        segments.append((name.rstrip(b'\0').decode(), va, fileoff, filesize))
    if command == 0x80000034:
        fixups, fixup_size = struct.unpack_from('<II', blob, position + 8)
    position += size
assert fixups is not None

def file_offset(va):
    matching = [off + va - start for _, start, off, size in segments if start <= va < start + size]
    assert len(matching) == 1
    return matching[0]

cfstring = 0x1002256d8
pointer_va = cfstring + 16
header = struct.unpack_from('<7I', blob, fixups)
starts = fixups + header[1]
segment_count = struct.unpack_from('<I', blob, starts)[0]
assert segment_count == len(segments)
segment_index = next(i for i, (_, va, _, size) in enumerate(segments) if va <= pointer_va < va + size)
relative = struct.unpack_from('<I', blob, starts + 4 + 4 * segment_index)[0]
assert relative
_, page_size, pointer_format, segment_offset, _, page_count = struct.unpack_from('<IHHQIH', blob, starts + relative)
assert pointer_format == 6  # DYLD_CHAINED_PTR_64_OFFSET: target is image relative.
assert segment_offset == segments[segment_index][1] - base
encoded = struct.unpack_from('<Q', blob, file_offset(pointer_va))[0]
assert encoded >> 63 == 0  # rebase, not import bind
assert (encoded >> 36) & 255 == 0  # no high-eight tagged address bits
string_va = base + (encoded & ((1 << 36) - 1))
length = struct.unpack_from('<Q', blob, file_offset(cfstring) + 24)[0]
text = blob[file_offset(string_va):file_offset(string_va) + length].decode('utf8')
assert text == 'Migration failed.'
record = dict(runtime_pc=trap['runtime_pc'], original_pc=hex(original_pc), slide=hex(slide),
    binary='/usr/libexec/mobileactivationd', binary_sha256=hashlib.sha256(blob).hexdigest(),
    original_instruction_unique_match=True, matched_bytes=len(needle),
    assertion_references=[dict(reference='0x1001bbb30', address='0x100208009', text='main'),
        dict(reference='0x1001bbb38', address=hex(cfstring), text=text,
             string_address=hex(string_va), length=length, pointer_format=pointer_format,
             chained_pointer=hex(encoded))],
    interpretation='Observed main() fatal path reports migration failure; its cause still requires service/runtime evidence.',
    other_process_slides_inferred=False, executable_modified=False, device_commands_executed=False)
out = DEV / 'build/display-analysis-ios16/u33-mobileactivation-trap.json'
out.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
