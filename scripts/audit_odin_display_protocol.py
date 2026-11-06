"""Qualify original iOS16 display selector rows and backend call sites.

No method name or usable prototype is inferred merely from a vtable slot.
The compiler separately checks dispatch and user-argument structure layouts.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
OUT = DEV/'build/display-analysis-ios16'
sys.path.insert(0, str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

audit = json.loads((OUT/'dispatch-discovery.json').read_text())
classes = {t.get('name'): t for t in audit['dispatch_candidates']}
client = classes['IOMobileFramebufferUserClient']
legacy = classes['IOMobileFramebufferLegacy']
path = DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho'
blob = path.read_bytes()
assert hashlib.sha256(blob).hexdigest() == audit['candidate_sha256']
image = np.macho(blob)
plan = json.loads(path.with_name('prelink-emission-report.json').read_text())
source = (DEV/'build/ios16-prelink/kernelcache.decompressed').read_bytes()
assert hashlib.sha256(source).hexdigest() == audit['original_sha256']
source_image = np.macho(source)


def read(va, size):
    at = np.backed_offset(image['segments'], va, size, len(blob))
    return blob[at:at+size]


def word(va):
    return struct.unpack('<I', read(va, 4))[0]


def pair(pc, register):
    a, b = struct.unpack('<II', read(pc, 8))
    assert a & 0x9f00001f == 0x90000000 | register
    assert b & 0xffc003ff == 0x91000000 | register << 5 | register
    immediate = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    return (pc & ~4095) + immediate*4096 + ((b >> 10) & 4095)


external = int(client['methods'][168]['address'], 16)
assert external == 0xfffffff004c012a0
# Actual unsigned range check and unchanged nonzero-provider gate.
assert word(external+0x54) == 0x71015d08  # subs w8,w8,#87
assert word(external+0x58) == 0x1a9f27e8  # cset w8,lo
assert read(external+0x7c, 16) == bytes.fromhex('006d40f9080040f908d942f900013fd6')
table = pair(external+0xf8, 9)
assert table == pair(external+0x164, 9) == pair(external+0x1dc, 9)
rows = []
extent = next(e for e in plan['extents'] if e['module'] == 'com.apple.iokit.IOMobileGraphicsFamily' and e['segment'] == '__TEXT_EXEC')
for selector in range(87):
    at = table+selector*24
    action, sin, bin_, sout, bout = struct.unpack('<Q4I', read(at, 24))
    original_at = np.backed_offset(source_image['segments'], at-plan['slide'], 24, len(source))
    original = struct.unpack_from('<Q4I', source, original_at)
    assert original[1:] == (sin, bin_, sout, bout)
    assert action == (original[0]+plan['slide'] if original[0] else 0)
    assert not action or extent['va'] <= action < extent['va']+extent['size']
    rows.append(dict(selector=selector, action=hex(action), scalar_input_count=sin,
        structure_input_bytes=bin_, scalar_output_count=sout, structure_output_bytes=bout))
# Dimensions: unmodified method reads two 32-bit members into independently
# null-checked x1/x2 output pointers. Record instruction evidence, not an
# iPadOS field-offset assumption.
dimension = int(legacy['methods'][246]['address'], 16)
assert read(dimension, 24) == bytes.fromhex('ff8300d1e00f00f9e10b00f9e20700f9e80f40f9e80300f9')
assert word(dimension+0x30) == 0xb9545908  # ldr w8,[x8,#5208]
assert word(dimension+0x38) == 0xb9000128  # str w8,[x9]
assert word(dimension+0x58) == 0xb9545d08  # ldr w8,[x8,#5212]
assert word(dimension+0x60) == 0xb9000128
# The original start method calls slot 274 then tests bit 0 of its return.
hardware_call = 0xfffffff004c0f5d4
assert read(hardware_call, 16) == bytes.fromhex('080040f9084944f900013fd6e0000037')
error_string = pair(hardware_call+24, 1)
error = read(error_string, 64).split(b'\0', 1)[0].decode()
assert error == 'start_hardware failed\n'
report = dict(scope='Static unchanged original protocol; no client runtime or display publication',
    target_os=audit['target_os'], candidate_sha256=audit['candidate_sha256'],
    original_sha256=audit['original_sha256'], selector_count=87,
    userclient_entries=187, external_method=hex(external), dispatch_table=hex(table),
    rows_preserved_from_original=True, methods=rows,
    provider_field=216, provider_pre_dispatch_slot=182,
    dimension_slot=246, dimension_method=hex(dimension), dimension_fields=dict(width=5208,height=5212),
    hardware_start_slot=274, hardware_start_callsite=hex(hardware_call+8),
    hardware_start_bit0_checked=True, hardware_start_failure_string=error,
    compiler_structure_check='OdinDisplayABIAnnotation.cpp compile-receipt.json',
    runtime_verified=False, backend_implemented=False, desktop_verified=False,
    device_commands_executed=False)
(OUT/'protocol-static-audit.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k != 'methods'}, indent=2))
