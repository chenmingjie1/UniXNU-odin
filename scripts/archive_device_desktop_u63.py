"""Preserve the native desktop loader work and actual verification evidence."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = ROOT / 'outputs/MIX4-UniXNU-device-desktop-u63'
OUT.mkdir(exist_ok=True)

def copy(source, name):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEV / source, target)

kernel = (DEV / 'build/display-owner-u62/kernel.prelinked.experimental.macho').read_bytes()
position = 32
for _ in range(struct.unpack_from('<I', kernel, 16)[0]):
    cmd, size = struct.unpack_from('<II', kernel, position)
    if cmd == 2:
        symoff, count, stroff, strsize = struct.unpack_from('<4I', kernel, position + 8)
    position += size
symbols = {}
for index in range(count):
    string, typ, sect, desc, value = struct.unpack_from('<IBBHQ', kernel, symoff + index * 16)
    if typ & 0xe == 0xe:
        end = kernel.index(0, stroff + string)
        symbols[kernel[stroff + string:end].decode(errors='replace')] = value
replays = []
for tag, symbol in [('u63physicaldtpe', '_wfe_timeout_init'),
                    ('u63physicaldttopology', '_ml_parse_cpu_topology'),
                    ('u63physicaldtirq', '_pe_arm_init_interrupts')]:
    data = json.loads((DEV / f'build/qemu-early-entry-{tag}/verification.json').read_text())
    pc = int(re.search(r'PC=([0-9a-fA-F]+)', data['registers']['return'])[1], 16)
    assert data['halted_before_symbol'] == symbol and pc == symbols[symbol]
    assert data['source_adt_sha256'] == data['replay_adt_sha256']
    assert not data['qemu_hardware_overlay'] and not data['qemu_vmm_present']
    replays.append({'tag': tag, 'reached_symbol': symbol, 'pc': hex(pc), 'unchanged_physical_adt': True})
    copy(f'build/qemu-early-entry-{tag}/verification.json', f'checks/{tag}.json')
copy('build/darwinboot-u63/DarwinBoot.efi', 'DarwinBoot.efi')
copy('build/darwinboot-u63/verification.json', 'driver-verification.json')
copy('build/darwinboot-u63/check/verification.json', 'checks/production-c-parsers.json')
copy('build/boot-abi-u63/verification.json', 'checks/boot-args-abi.json')
copy('build/device-desktop-u63/manifest.json', 'staged-media-manifest.json')
for name in ('kernel.macho.adt',):
    copy('build/device-desktop-u63/esp/EFI/UniXNU/Payloads/' + name, 'payload/' + name)
copy('build/device-desktop-u63/esp/EFI/UniXNU/unixnu.toml', 'payload/unixnu.toml')
for name in ('build_darwinboot_windows.py', 'stage_darwinboot_desktop_media.py',
             'prepare_device_desktop_u63.py', 'check_darwinboot_desktop_media.py',
             'check_boot_args_abi.py', 'adt_codec.py', 'archive_device_desktop_u63.py'):
    copy('scripts/' + name, 'source/' + name)
for path in (DEV / 'build/darwinboot-u63/source').iterdir():
    copy(str(path.relative_to(DEV)), 'staged-source/' + path.name)
copy('firmware/OdinDesktopMedia.h', 'source/OdinDesktopMedia.h')
shutil.copy2(ROOT / 'work/UniXNU-components/DarwinBoot-3c75734014cdab0acd9541e88057b7606ee7ae08/LICENSE',
             OUT / 'LICENSE.DarwinBoot')
report = dict(status='Native loader and desktop file set built; physical transport integration pending',
              device='Xiaomi MIX 4 / odin', os='iOS16.5/20F66',
              desktop_verified_on_computer=True, physical_desktop_verified=False,
              phone_boot_image=False, device_commands_executed=False, partition_writes_executed=False,
              exact_physical_adt_cpu_replays=replays,
              early_PE_init_platform_hang_proven=False,
              remaining='Provide RAM-uploaded System/Data through real UEFI file services, integrate firmware, then qualify physical boot',
              source_media_not_duplicated=True)
(OUT / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
(OUT / 'README.md').write_text('''# MIX 4 UniXNU u63 desktop loader work

ARM64 DarwinBoot has been built with large raw System and separate Data handoff.
It streams `kernel.macho.system` and `kernel.macho.data` into its allocated
window in at most 1 MiB reads; partial reads fail before ExitBootServices.
The old Request.Ramdisk API remains supported. Raw input is bounded at 3 GiB;
packed input retains its upstream 256 MiB bound. Data is raw, at most 512 MiB.
The Data descriptor must be a unique zeroed 16-byte property at
`/chosen/memory-map/OdinDataRAMDisk`. The entire media range is reserved below
topOfKernelData. Allocation still requires one actual conventional-memory run.

The staged full file set is in `work/UniXNU-odin/build/device-desktop-u63/esp`.
System and Data there are immutable hardlinks to exact u62 inputs. Never edit
those files in place. Runtime changes go into a separate private RAM copy.
No file set or driver here is an Android boot.img. No phone commands were run.
The real RAM upload/UEFI filesystem connection remains to be implemented.

Checks execute the staged production C parsers and streaming functions, reject
all 11,760 truncated ADTs and malformed Data descriptors, verify full chunked
copy, reject short reads, and compare all 13 boot-argument ABI fields.
Three computer CPU replays retain the original physical device tree exactly;
the final replay reaches the GIC initialization entrance. They do not execute
the phone's GIC or qualify physical scanout, touch or GPU.

Build/check commands from `work/UniXNU-odin`:
```
python scripts/build_darwinboot_windows.py --tag u63 --desktop-media
python scripts/check_darwinboot_desktop_media.py
python scripts/check_boot_args_abi.py --darwinboot-tag u63
python scripts/prepare_device_desktop_u63.py
python scripts/archive_device_desktop_u63.py
```

Based on pinned UniXNU/DarwinBoot 3c75734014cdab0acd9541e88057b7606ee7ae08.
The upstream checkout is unchanged; odin changes are applied only in staging.
''')
files = []
for path in sorted(OUT.rglob('*')):
    if path.is_file() and path.name != 'manifest.json':
        files.append({'path': str(path.relative_to(OUT)), 'bytes': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(OUT / 'manifest.json').write_text(json.dumps({'schema': 1, 'files': files}, indent=2) + '\n')
print(json.dumps(report, indent=2))
