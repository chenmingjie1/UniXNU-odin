"""Point explicit development PID1 at the cache actually carried by this root."""
from pathlib import Path
import difflib
import json

root = Path('/home/odin/unixnu-odin-build')
out = root/'evidence/odin-cache-directory-u10'
out.mkdir(exist_ok=False)
path = root/'upstream/.cache/xnu-work/bsd/kern/kern_exec.c'
before = path.read_text()
anchor = '\t\t/* The boot tunable itself does not call the commpage exporter. */'
assert before.count(anchor) == 1
addition = '''		int odin_cache_directory = 0;
		if (PE_parse_boot_argn("odin-cache-directory", &odin_cache_directory,
		    sizeof(odin_cache_directory)) && odin_cache_directory) {
			if (odin_cache_directory != 1 || init_envp != USER_ADDR_NULL) {
				panic("unsupported odin cache environment composition");
			}
			const char *cache_environment = "DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld";
			vnode_t cache_probe = NULLVP;
			error = vnode_lookup("/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64",
			    0, &cache_probe, vfs_context_current());
			if (error) panic("odin development shared cache missing: %d", error);
			vnode_put(cache_probe);
			user64_addr_t environment_vector[2] = {scratch_addr + 0x400, USER_ADDR_NULL};
			error = copyout(cache_environment, environment_vector[0], strlen(cache_environment) + 1);
			if (!error) error = copyout(environment_vector, scratch_addr + 0x500, sizeof(environment_vector));
			if (error) panic("odin cache environment copyout failed: %d", error);
			init_envp = scratch_addr + 0x500;
			printf("odin development cache directory: /System/Cryptexes/OS/System/Library/Caches/com.apple.dyld\\n");
		}
'''
after = before.replace(anchor, addition+anchor)
(out/'kern_exec.c.before').write_text(before)
path.write_text(after)
(out/'odin-cache-directory.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True), fromfile='a/bsd/kern/kern_exec.c', tofile='b/bsd/kern/kern_exec.c')))
(out/'verification.json').write_text(json.dumps({
    'selector':'odin-cache-directory=1', 'development_init_only':True,
    'cache_path_checked_by_vnode_lookup':True,
    'signature_checks_unchanged':True, 'runtime_verified':False,
    'device_commands_executed':False}, indent=2)+'\n')
print('Explicit development cache directory installed')
