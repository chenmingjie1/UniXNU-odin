"""Stage real desktop inputs with physical odin resources, without phone I/O.

This is a complete file set for a UEFI filesystem provider, not an Android boot
image. System and Data are immutable hardlinks to already qualified inputs.
"""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import struct
import tomllib
from adt_codec import decode, encode, lookup

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = DEV / 'build/device-desktop-u63'
ESP = OUT / 'esp/EFI/UniXNU'
PAYLOAD = ESP / 'Payloads'
PAYLOAD.mkdir(parents=True, exist_ok=True)
verified = json.loads((DEV / 'build/qemu-early-entry-u62nopasscode/verification.json').read_text())
physical_path = DEV / 'build/prelinked-payload-u08/esp/EFI/UniXNU/Payloads/kernel.macho.adt'
tree = decode(physical_path.read_bytes())
original = copy.deepcopy(tree)
desktop = decode((DEV / 'build/qemu-early-entry-u62nopasscode/replay.adt').read_bytes())
chosen = lookup(tree, 'chosen')
userland = lookup(desktop, 'chosen')
# Only OS identity/manifest/display fields; no copied QEMU hardware resources.
allowed = ('mix-n-match-prevention-status', 'odin-development-boot', 'boot-manifest-hash',
           'owner-boot-manifest-domain', 'display-scale', 'display-rotation',
           'mac-address-wifi0', 'mac-address-bluetooth0')
for name in allowed:
    chosen[name] = userland[name]
chosen['darwinboot-memory-size'] = struct.pack('<Q', 0x100000000)
lookup(tree, 'chosen', 'manifest-properties').update(lookup(desktop, 'chosen', 'manifest-properties'))
lookup(tree, 'chosen', 'memory-map').update({name: bytes(16) for name in ('RAMDisk', 'OdinDataRAMDisk', 'TrustCache')})
lookup(tree, 'defaults')['sleep-disabled'] = struct.pack('<I', 1)
tree[1].append(({'name': b'filesystems\0', 'DoNotUseSEP': struct.pack('<I', 1)}, []))
for name in ('arm-io', 'cpus'):
    def child(t):
        return next(n for n in t[1] if n[0]['name'] == name.encode() + b'\0')
    assert encode(child(tree)) == encode(child(original)), 'Physical hardware resources changed'
assert 'vmm-present' not in lookup(tree, 'defaults')
(PAYLOAD / 'kernel.macho.adt').write_bytes(encode(tree))

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()

inputs = {
    'Payloads/kernel.macho': DEV / 'build/display-owner-u62/kernel.prelinked.experimental.macho',
    'Payloads/kernel.macho.system': DEV / 'build/root-media/system-host-input-u59.apfs',
    'Payloads/kernel.macho.data': DEV / 'build/qemu-early-entry-u49upstreamsetup/data-after.apfs',
    'Payloads/kernel.macho.trustcache': DEV / 'build/root-media/host-input-development-trust-u59.bundle',
    'DarwinBoot.efi': DEV / 'build/darwinboot-u63/DarwinBoot.efi',
}
files = []
for name, source in inputs.items():
    target = ESP / name
    if name.endswith(('.system', '.data')):
        if not target.exists():
            target.hardlink_to(source)
    else:
        shutil.copy2(source, target)
    digest = sha(target)
    assert digest == sha(source)
    files.append({'path': str(target.relative_to(OUT)), 'source': str(source), 'bytes': target.stat().st_size,
                  'sha256': digest, 'immutable_input': True})
assert files[0]['sha256'] == verified['kernel_sha256']
assert files[1]['bytes'] == verified['ramdisk_bytes']
assert files[2]['sha256'] == verified['data_ramdisk_sha256']
assert files[3]['sha256'] == verified['trust_cache_sha256']
arguments = verified['boot_args']
assert len(arguments.encode()) < 608
config = '''version = 1
[boot]
timeout = 10
fallback_timeout = -1
default = "odin-desktop"
[ui]
title = "MIX 4 - UniXNU desktop candidate (unqualified)"
[kits]
autoload = false
[[entry]]
id = "odin-desktop"
title = "iOS 16.5 RAM desktop candidate"
type = "xnu"
path = "Payloads/kernel.macho"
args = "''' + arguments + '''"
'''
assert 'initrd' not in tomllib.loads(config)['entry'][0], 'Raw root is streamed by DarwinBoot, not preallocated by UniXNU'
(ESP / 'unixnu.toml').write_text(config)
kernel = inputs['Payloads/kernel.macho'].read_bytes()
base = end = None
position = 32
for _ in range(struct.unpack_from('<I', kernel, 16)[0]):
    cmd, size = struct.unpack_from('<II', kernel, position)
    if cmd == 25:
        address, span = struct.unpack_from('<QQ', kernel, position + 24)
        if span:
            base = address if base is None else min(base, address)
            end = address + span if end is None else max(end, address + span)
    position += size
align = lambda n, a: (n + a - 1) & -a
tree_offset = align(end - base, 0x4000) + 4096
system_offset = align(tree_offset + len(encode(tree)), 4096)
data_offset = system_offset + files[1]['bytes']
trust_offset = data_offset + files[2]['bytes']
used = align(trust_offset + files[3]['bytes'], 0x4000)
assert used + 0x200000 < 0x100000000
report = dict(schema=1, tag='u63', device='odin', os='iOS16.5/20F66', files=files,
    hardware_adt_sha256=sha(physical_path), staged_adt_sha256=sha(PAYLOAD / 'kernel.macho.adt'),
    physical_gic_and_cpu_unchanged=True, qemu_vmm_present=False,
    requested_window_bytes=0x100000000, reserved_input_bytes=used,
    remaining_kernel_memory_bytes=0x100000000-used,
    temporary_full_system_allocation=False, temporary_full_data_allocation=False,
    root_read_only_file=True, data_private_ram_copy=True, initrd_preallocation=False,
    phone_boot_image=False, flash_ready=False, device_commands_executed=False,
    host_desktop_verified=True, physical_desktop_verified=False,
    remaining=['Expose these files through a physical UEFI filesystem using RAM upload without a multi-GB boot image',
               'Validate actual firmware conventional-memory allocation and GIC/runtime on SM8350',
               'Qualify physical scanout, native touch and A660 independently'])
(OUT / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'}, indent=2))
