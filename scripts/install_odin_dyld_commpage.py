"""Publish the existing dyld_flags boot tunable before development PID1 exec."""
from pathlib import Path
import difflib
import hashlib
import json

root = Path('/home/odin/unixnu-odin-build')
out = root/'evidence/odin-dyld-commpage-u10'
out.mkdir(exist_ok=False)
path = root/'upstream/.cache/xnu-work/bsd/kern/kern_exec.c'
before = path.read_text()
anchor = '\t\tprintf("load_init_program: owner development entry %s\\n", odin_init);'
assert before.count(anchor) == 1
addition = '''		/* The boot tunable itself does not call the commpage exporter. */
		extern uint64_t dyld_flags;
		extern void commpage_update_dyld_flags(uint64_t);
		commpage_update_dyld_flags(dyld_flags);
		printf("odin development dyld commpage flags: 0x%llx\\n", dyld_flags);
'''
after = before.replace(anchor, addition+anchor)
(out/'kern_exec.c.before').write_text(before)
path.write_text(after)
(out/'odin-dyld-commpage.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/bsd/kern/kern_exec.c', tofile='b/bsd/kern/kern_exec.c')))
(out/'verification.json').write_text(json.dumps({
    'sha256':hashlib.sha256(after.encode()).hexdigest(),
    'development_init_only':True, 'existing_tunable':'dyld_flags',
    'exports_existing_value_without_forcing_bits':True,
    'security_exemptions_added':False, 'runtime_verified':False,
    'device_commands_executed':False}, indent=2)+'\n')
print('Existing dyld flags now exported before explicit development init')
