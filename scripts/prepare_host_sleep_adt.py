"""Use XNU's existing sleep-disabled default in a separate QEMU-only ADT.

The pinned ios-fuxi sleep patch documents this original device-tree setting.
No new sleep/wake implementation or phone configuration is claimed.
"""
from pathlib import Path
import bisect
import copy
import hashlib
import json
import struct
from adt_codec import decode, encode, lookup

DEV = Path(__file__).resolve().parents[1]
source = DEV / 'build/display-analysis-ios16/u34-host-network.adt'
output = DEV / 'build/display-analysis-ios16/u53-host-awake.adt'
assert not output.exists()
kernel = DEV / 'build/display-owner-u31/kernel.prelinked.experimental.macho'
blob = kernel.read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'ab67534e74266878a8f13a58c533885c82217a5b9f02f85df0f77fb33dae03a4'
segments, symbols = [], []
at = 32
for _ in range(struct.unpack_from('<I', blob, 16)[0]):
    cmd, size = struct.unpack_from('<II', blob, at)
    if cmd == 0x19:
        name = blob[at + 8:at + 24].split(b'\0')[0].decode()
        va, vs, off, fs = struct.unpack_from('<4Q', blob, at + 24)
        segments.append((name, va, off, fs))
    elif cmd == 2:
        so, count, st, _ = struct.unpack_from('<4I', blob, at + 8)
    at += size
for i in range(count):
    no, kind, _, _, value = struct.unpack_from('<IBBHQ', blob, so + i * 16)
    if kind & 14 == 14:
        name = blob[st + no:blob.index(0, st + no)].decode()
        if name:
            symbols.append((value, name))
symbols.sort()
addresses = [row[0] for row in symbols]
string_off = blob.index(b'sleep-disabled\0')
string_va = next(va + string_off - off for _, va, off, fs in segments if off <= string_off < off + fs)
xrefs = []
for name, va, off, fs in segments:
    if name != '__TEXT_EXEC':
        continue
    for p in range(off, off + fs - 8, 4):
        adrp, add = struct.unpack_from('<2I', blob, p)
        if adrp & 0x9f000000 != 0x90000000 or add & 0xffc00000 != 0x91000000:
            continue
        reg = adrp & 31
        if (add >> 5) & 31 != reg:
            continue
        pc = va + p - off
        imm = ((adrp >> 29) & 3) | (((adrp >> 5) & 0x7ffff) << 2)
        if imm & 0x100000:
            imm -= 0x200000
        if (pc & ~4095) + (imm << 12) + ((add >> 10) & 4095) != string_va:
            continue
        symbol = symbols[bisect.bisect_right(addresses, pc) - 1]
        xrefs.append(dict(pc=hex(pc), function=symbol[1], function_offset=hex(pc - symbol[0]),
                          instructions=blob[p:p + 8].hex()))
assert any('IOPMrootDomain' in row['function'] for row in xrefs), xrefs
before = decode(source.read_bytes())
tree = copy.deepcopy(before)
defaults = lookup(tree, 'defaults')
assert 'sleep-disabled' not in defaults
defaults['sleep-disabled'] = struct.pack('<I', 1)
result = encode(tree)
check = decode(result)
assert lookup(check, 'defaults').pop('sleep-disabled') == struct.pack('<I', 1)
assert check == before
output.write_bytes(result)
receipt = dict(scope='Host QEMU sleep prevention only; not a phone ADT',
    source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    output=str(output), sha256=hashlib.sha256(result).hexdigest(),
    changed_properties={'defaults/sleep-disabled': '01000000'}, all_other_properties_preserved=True,
    kernel_sha256=hashlib.sha256(blob).hexdigest(), original_kernel_key_xrefs=xrefs,
    reference='bangprovn/ios-fuxi@27f6a31c8b27c6f9127f9cf27092968422579ccf/xnu/patches/0105-fuxi-idle.patch',
    original_xnu_reader='IOPMrootDomain::dispatchPowerEvent: PE_get_default(sleep-disabled, &gSleepDisabledFlag, sizeof(gSleepDisabledFlag))',
    evidence='u52b: PMRD System Sleep, IOCPUSleepKernel enter, final PC ArmCpu::haltCPU+0x48',
    kernel_unchanged=True, device_commands_executed=False, runtime_verified=False, desktop_verified=False)
output.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
