"""Instrument the host-only Data mount without changing VFS return values."""
from pathlib import Path
import difflib
import hashlib
import json

root = Path('/home/odin/unixnu-odin-build')
tree = root / 'upstream/.cache/xnu-work'
out = root / 'evidence/odin-data-preflight-u12'
out.mkdir(exist_ok=False)


def save(name, before, after):
    assert before != after
    (out / (Path(name).name + '.before')).write_text(before)
    (tree / name).write_text(after)
    with (out / 'odin-data-preflight.patch').open('a') as stream:
        stream.write(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile='a/' + name, tofile='b/' + name)))


name = 'bsd/kern/kern_exec.c'
before = (tree / name).read_text()
anchor = 'volatile int native_owner_data_stage = 0;'
assert before.count(anchor) == 1
after = before.replace(anchor, anchor + '''
volatile int odin_data_device_lookup = -1;
volatile int odin_data_target_lookup = -1;
volatile int odin_data_device_type = -1;
volatile int odin_data_device_matches = -1;
''')
anchor = '\tnative_owner_data_stage = 2;\n\terror = mount(p, &request, &result);'
assert after.count(anchor) == 1
after = after.replace(anchor, '''
#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
	vnode_t odin_probe = NULLVP;
	odin_data_device_lookup = vnode_lookup(device_path, 0, &odin_probe, vfs_context_current());
	if (!odin_data_device_lookup) {
		odin_data_device_type = vnode_vtype(odin_probe);
		odin_data_device_matches = vnode_specrdev(odin_probe) == device;
		vnode_put(odin_probe);
	}
	odin_probe = NULLVP;
	odin_data_target_lookup = vnode_lookup("/private/var", 0, &odin_probe, vfs_context_current());
	if (!odin_data_target_lookup) vnode_put(odin_probe);
	printf("odin Data preflight: device=%d type=%d matches=%d target=%d\\n",
	    odin_data_device_lookup, odin_data_device_type, odin_data_device_matches, odin_data_target_lookup);
#endif
	native_owner_data_stage = 2;
	error = mount(p, &request, &result);
	printf("odin Data mount returned: %d\\n", error);''')
save(name, before, after)

name = 'bsd/vfs/vfs_syscalls.c'
before = (tree / name).read_text()
anchor = '\t\terror = VFS_MOUNT(mp, device_vnode, fsmountargs, ctx);'
assert before.count(anchor) == 1
after = before.replace(anchor, '''#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
		uint32_t odin_trace_mount = 0;
		PE_parse_boot_argn("odin-data-mount", &odin_trace_mount, sizeof(odin_trace_mount));
		if (odin_trace_mount == 1)
			printf("odin VFS mount enter: fs=%s from=%s args=%llx devvp=%p\\n",
			    fstypename, mp->mnt_vfsstat.f_mntfromname, fsmountargs, device_vnode);
#endif
''' + anchor + '''
#if (DEBUG || DEVELOPMENT) && defined(ARM64_BOARD_CONFIG_BCM2837)
		if (odin_trace_mount == 1) printf("odin VFS mount return: %d\\n", error);
#endif''')
save(name, before, after)
(out / 'verification.json').write_text(json.dumps({
    'scope': 'Development host Data path diagnostics only',
    'device_commands_executed': False,
    'mount_result_unmodified': True,
    'patch_sha256': hashlib.sha256((out / 'odin-data-preflight.patch').read_bytes()).hexdigest(),
}, indent=2) + '\n')
print('Data mount preflight installed; not yet compiled or replayed')
