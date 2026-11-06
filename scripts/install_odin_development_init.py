"""Select the audited dynamic launchd in an explicit DEVELOPMENT boot only.

This adds no signing exemption. The normal exec/AMFI path still runs, and
the default launchd selection is unchanged unless the exact opt-in is used.
"""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT/'upstream/.cache/xnu-work'
OUT = ROOT/'evidence/odin-development-init-u10'
OUT.mkdir(exist_ok=False)
name = 'bsd/kern/kern_exec.c'
path = TREE/name
before = path.read_text()
anchor = '#if DEBUG || DEVELOPMENT\n\t/* Check for boot-arg suffix first */'
assert before.count(anchor) == 1
replacement = '''#if DEBUG || DEVELOPMENT
#if defined(ARM64_BOARD_CONFIG_BCM2837)
	/* Explicit owner development entry; retain the normal exec/AMFI checks. */
	char odin_init[64];
	if (PE_parse_boot_argn("odin-init-path", odin_init, sizeof(odin_init))) {
		if (strcmp(odin_init, "/sbin/launchd.ios") != 0) {
			panic("unsupported odin development init path");
		}
		printf("load_init_program: owner development entry %s\\n", odin_init);
		error = load_init_program_at_path(p, (user_addr_t)scratch_addr,
		    odin_init, init_envp);
		if (error) panic("owner development init exec failed: %d", error);
		return;
	}
#endif
	/* Check for boot-arg suffix first */'''
after = before.replace(anchor, replacement)
(OUT/'kern_exec.c.before').write_text(before)
path.write_text(after)
(OUT/'odin-development-init.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True), fromfile='a/'+name, tofile='b/'+name)))
(OUT/'verification.json').write_text(json.dumps({
    'path': name, 'sha256': hashlib.sha256(after.encode()).hexdigest(),
    'selector': 'odin-init-path=/sbin/launchd.ios',
    'development_only': True, 'normal_exec_security_checks_preserved': True,
    'device_commands_executed': False, 'runtime_verified': False}, indent=2)+'\n')
print('Explicit development init selector installed; rebuild required')
