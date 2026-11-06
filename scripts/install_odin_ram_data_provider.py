"""Select the statically qualified original IOKit-backed host Data provider."""
from pathlib import Path
import difflib
import json

root = Path('/home/odin/unixnu-odin-build')
out = root / 'evidence/odin-ram-data-provider-u12'
out.mkdir(exist_ok=False)
path = root / 'upstream/.cache/xnu-work/bsd/kern/kern_exec.c'
before = path.read_text()
anchor = '#ifndef XNU_OWNER_DATA_VOLUME_UUID\n#error Supply the observed scratch volume UUID for the IOKit backend'
assert before.count(anchor) == 1
after = before.replace(anchor, '''#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
#define XNU_OWNER_DATA_VOLUME_UUID "27931BBD-B7C9-B784-FA28-8FFFFE8261CC"
#endif
''' + anchor)
(out / 'kern_exec.c.before').write_text(before)
path.write_text(after)
(out / 'odin-ram-data-provider.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/bsd/kern/kern_exec.c', tofile='b/bsd/kern/kern_exec.c')))

path = root / 'link_offline_kernel.sh'
before = path.read_text()
assert 'ram-block/libRamBlock.a' not in before
after = before.replace('libpthread-kernel/libpthread_kernel.a; do',
                       'libpthread-kernel/libpthread_kernel.a ram-block/libRamBlock.a; do')
after = after.replace('kern_exec.o_CFLAGS_ADD=',
                       'KernelConfigTables.cpo_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1 \\\n  kern_exec.o_CFLAGS_ADD=')
after = after.replace('-DXNU_OWNER_DATA_MOUNT=1 -DXNU_OWNER_BOOT_MANIFEST=1',
                       '-DXNU_OWNER_DATA_MOUNT=1 -DXNU_OWNER_BOOT_MANIFEST=1 -DXNU_NATIVE_RAM_BLOCK=1')
(out / 'link_offline_kernel.sh.before').write_text(before)
path.write_text(after)
(out / 'link_offline_kernel.sh').write_text(after)
# The XNU make rule does not track per-object flag changes as dependencies.
(root / 'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/KernelConfigTables.cpo').unlink(missing_ok=True)
(out / 'verification.json').write_text(json.dumps({
    'scope': 'Development QEMU isolated RAM Data only',
    'data_uuid': '27931BBD-B7C9-B784-FA28-8FFFFE8261CC',
    'device_commands_executed': False,
    'live_metadata_verified': False, 'data_mount_verified': False,
}, indent=2) + '\n')
print('Selected concrete IOKit RAM Data provider; compile and runtime remain unverified')
