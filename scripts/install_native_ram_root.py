"""Wire DarwinBoot's reserved raw RAMDisk to XNU's existing md driver.

Computer build only. The md0 node is read-only. No storage/flash driver is
enabled and no unsigned physical-memory boot arguments are accepted.
"""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

root = Path('/home/odin/unixnu-odin-build')
tree = root / 'upstream/.cache/xnu-work'
out = root / 'evidence/odin-ram-root-u09'
out.mkdir(exist_ok=False)
path = tree / 'bsd/dev/memdev.c'
before = path.read_text()
shutil.copy2(path, out / 'memdev.c.before')
header = Path(__file__).with_name('OdinRamRootRange.h').read_text()
destination = tree / 'bsd/dev/OdinRamRootRange.h'
assert not destination.exists()
destination.write_text(header)
needle = 'void            mdevinit(int the_cnt);'
assert before.count(needle) == 1
text = before.replace(needle, '''#include <pexpert/device_tree.h>
#include <pexpert/boot.h>
#include "OdinRamRootRange.h"
extern boot_args *BootArgs;
static void odin_ram_root_init(void);
unsigned int odin_ram_root_status;
uint64_t odin_ram_root_base;
uint64_t odin_ram_root_bytes;

''' + needle)
needle = 'mdevinit(__unused int the_cnt)\n{'
assert text.count(needle) == 1
text = text.replace(needle, needle + '\n\todin_ram_root_init();')
needle = 'dev_t\nmdevlookup(int devid)'
assert text.count(needle) == 1
text = text.replace(needle, '''/* Raw boot media reserved by DarwinBoot through TopOfKernelData. */
static void
odin_ram_root_init(void)
{
	DTEntry entry;
	const void *property;
	unsigned int size;
	uint64_t range[2], virt_tree, phys_tree;
	dev_t device;

	odin_ram_root_status = 1; /* No disk in this payload. */
	if (SecureDTLookupEntry(NULL, "/chosen/memory-map", &entry) != kSuccess ||
	    SecureDTGetProperty(entry, "RAMDisk", &property, &size) != kSuccess) {
		return;
	}
	if (size != sizeof(range) || !BootArgs) {
		panic("odin RAM root: malformed memory-map descriptor");
	}
	memcpy(range, property, sizeof(range));
	virt_tree = (uint64_t)(uintptr_t)BootArgs->deviceTreeP;
	if (virt_tree < BootArgs->virtBase ||
	    virt_tree - BootArgs->virtBase > UINT64_MAX - BootArgs->physBase) {
		panic("odin RAM root: invalid device-tree translation");
	}
	phys_tree = BootArgs->physBase + virt_tree - BootArgs->virtBase;
	if (!odin_ram_root_range_valid(BootArgs->physBase, BootArgs->memSize,
	    BootArgs->topOfKernelData, phys_tree, BootArgs->deviceTreeLength,
	    range[0], range[1])) {
		panic("odin RAM root: disk is outside reserved payload memory");
	}
	odin_ram_root_status = 2;
	device = mdevadd(0, range[0] >> 12, (unsigned int)(range[1] >> 12), 1);
	if (device == (dev_t)-1) {
		panic("odin RAM root: md0 registration failed");
	}
	mdev[0].mdFlags |= mdRO;
	odin_ram_root_base = range[0];
	odin_ram_root_bytes = range[1];
	odin_ram_root_status = 3;
}

''' + needle)
path.write_text(text)
patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='a/bsd/dev/memdev.c', tofile='b/bsd/dev/memdev.c'))
patch += ''.join(difflib.unified_diff([], header.splitlines(True),
    fromfile='/dev/null', tofile='b/bsd/dev/OdinRamRootRange.h'))
(out / 'odin-native-ram-root.patch').write_text(patch)
(out / 'verification.json').write_text(json.dumps({
    'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
    'validator_sha256': hashlib.sha256(header.encode()).hexdigest(),
    'boot_protocol': 'DarwinBoot /chosen/memory-map/RAMDisk, two little-endian u64 fields',
    'node': 'md0', 'read_only': True, 'physical_boot_arguments_enabled': False,
    'raw_apfs_mount_verified': False, 'device_commands_executed': False,
}, indent=2) + '\n')
print('Native reserved RAM root integration installed; compile and runtime qualification required')
