"""Add an opt-in, reserved RAM Data device and reuse native APFS mounting.

Build-host script. No storage provider or physical-address boot arg is enabled.
The new path is DEVELOPMENT-only and requires odin-data-mount=1 plus the
separate memory-map descriptor. md0 remains read-only.
"""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT / 'upstream/.cache/xnu-work'
OUT = ROOT / 'evidence/odin-host-data-u11'
OUT.mkdir(exist_ok=False)


def save(name, before, after):
    assert before != after
    (OUT / (Path(name).name + '.before')).write_text(before)
    (TREE / name).write_text(after)
    patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile='a/' + name, tofile='b/' + name))
    with (OUT / 'odin-host-data.patch').open('a') as stream:
        stream.write(patch)


name = 'bsd/dev/memdev.c'
before = (TREE / name).read_text()
anchor = 'static void odin_ram_root_init(void);'
assert before.count(anchor) == 1
after = before.replace(anchor, anchor + '\nstatic void odin_ram_data_init(void);\nunsigned int odin_ram_data_status;')
anchor = '\todin_ram_root_init();'
assert after.count(anchor) == 1
after = after.replace(anchor, anchor + '\n\todin_ram_data_init();')
anchor = 'dev_t\nmdevlookup(int devid)'
assert after.count(anchor) == 1
new = '''/* A second, non-overlapping reserved RAM range; never Android storage. */
static void
odin_ram_data_init(void)
{
#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
	uint32_t enabled = 0;
	if (!PE_parse_boot_argn("odin-data-mount", &enabled, sizeof(enabled)) || enabled != 1) return;
	DTEntry entry;
	const void *property;
	unsigned int size;
	uint64_t range[2], virt_tree, phys_tree, virtual_base;
	odin_ram_data_status = 1;
	if (!BootArgs || SecureDTLookupEntry(NULL, "/chosen/memory-map", &entry) != kSuccess ||
	    SecureDTGetProperty(entry, "OdinDataRAMDisk", &property, &size) != kSuccess || size != sizeof(range)) {
		panic("odin RAM Data: descriptor missing");
	}
	memcpy(range, property, sizeof(range));
	virt_tree = (uint64_t)(uintptr_t)BootArgs->deviceTreeP;
	if (virt_tree < BootArgs->virtBase || virt_tree - BootArgs->virtBase > UINT64_MAX - BootArgs->physBase)
		panic("odin RAM Data: invalid device-tree translation");
	phys_tree = BootArgs->physBase + virt_tree - BootArgs->virtBase;
	if (!odin_ram_root_range_valid(BootArgs->physBase, BootArgs->memSize,
	    BootArgs->topOfKernelData, phys_tree, BootArgs->deviceTreeLength, range[0], range[1]) ||
	    odin_ram_root_status != 3 || range[0] < odin_ram_root_base + odin_ram_root_bytes ||
	    range[1] > UINT64_C(0x20000000) || range[0] - BootArgs->physBase > UINT64_MAX - BootArgs->virtBase) {
		panic("odin RAM Data: invalid or overlapping reserved range");
	}
	virtual_base = BootArgs->virtBase + range[0] - BootArgs->physBase;
	if (mdevadd(2, virtual_base >> 12, (unsigned int)(range[1] >> 12), 0) == (dev_t)-1)
		panic("odin RAM Data: md2 registration failed");
	odin_ram_data_status = 3;
	printf("odin RAM Data: md2 registered, %llu bytes; md0 remains read-only\\n", range[1]);
#endif
}

'''
after = after.replace(anchor, new + anchor)
save(name, before, after)

name = 'bsd/kern/kern_exec.c'
before = (TREE / name).read_text()
# Only the fallback Data provider changes; shared/root providers are untouched.
anchor = '\tdevice = mdevlookup(0);\n\tif (device == NODEV || mdevgetrange(0, &base, &size)'
assert before.count(anchor) == 1
after = before.replace(anchor, '\tstrlcpy(device_path, "/dev/md2", sizeof(device_path));\n\tdevice = mdevlookup(2);\n\tif (device == NODEV || mdevgetrange(2, &base, &size)')
start = '#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT\n\tboot_progress_stage("Data mount enter");'
assert after.count(start) == 1
after = after.replace(start, '''#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT
	uint32_t odin_data_mount = 0;
#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
	if (PE_parse_boot_argn("odin-data-mount", &odin_data_mount, sizeof(odin_data_mount)) && odin_data_mount == 1) {
#else
	if (0) {
#endif
	boot_progress_stage("Data mount enter");''')
anchor = '\tif (data_error) panic("offline scratch Data mount failed: %d", data_error);'
assert after.count(anchor) == 1
after = after.replace(anchor, anchor + '\n\tprintf("odin RAM Data: native APFS rw mount verified at /private/var\\n");')
anchor = '\tboot_progress_stage("temporary watchdog launch policy ready");\n#endif\n#endif'
assert after.count(anchor) == 1
after = after.replace(anchor, '\tboot_progress_stage("temporary watchdog launch policy ready");\n#endif\n\t}\n#endif')
anchor = '\tif (!error) native_gpu_addon_prepare(p, scratch);'
assert after.count(anchor) == 1
after = after.replace(anchor, '''#if defined(XNU_NATIVE_RAM_BLOCK) && XNU_NATIVE_RAM_BLOCK
	if (!error) native_gpu_addon_prepare(p, scratch);
#endif''')
save(name, before, after)
(OUT / 'verification.json').write_text(json.dumps({
    'development_only': True, 'boot_arg': 'odin-data-mount=1',
    'descriptor': '/chosen/memory-map/OdinDataRAMDisk',
    'root_read_only': True, 'data_device': '/dev/md2',
    'data_limit_bytes': 512 * 1024 * 1024,
    'device_commands_executed': False, 'runtime_verified': False,
    'patch_sha256': hashlib.sha256((OUT / 'odin-host-data.patch').read_bytes()).hexdigest(),
}, indent=2) + '\n')
print('Reserved RAM Data integration installed; compilation and RW mount unverified')
