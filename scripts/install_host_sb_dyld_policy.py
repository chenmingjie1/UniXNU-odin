"""Development-only SpringBoard path-variable permission with original AMFI result.

Uses the 0x5a ABI from pinned HakiOS kern_minimac.c and bit 1 from Apple's
dyld-1066.8/DyldProcessConfig.cpp. No global policy replacement or 0xff grant.
"""
from pathlib import Path
import argparse, difflib, hashlib, json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', required=True)
a = p.parse_args()
assert a.tag.isalnum()
base = Path('/home/odin/unixnu-odin-build')
out = base / ('evidence/odin-display-owner-' + a.tag)
out.mkdir(parents=True, exist_ok=True)
source = base / 'upstream/.cache/xnu-work/security/mac_base.c'
before = source.read_text()
assert 'ODIN_SB_DYLD_U61' not in before
anchor = '#include <sys/proc.h>'
assert before.count(anchor) == 1
after = before.replace(anchor, anchor + '\n#include <pexpert/pexpert.h>')
start = after.index('__mac_syscall(proc_t p,')
end = after.index('\nint\nmac_mount_label_get', start)
function = after[start:end]
anchor = 'done:\n\treturn error;'
assert function.count(anchor) == 1
hook = '''done:
#if DEBUG || DEVELOPMENT
    /* ODIN_SB_DYLD_U61: retain original checks/result, and change only the
     * path-variable bit for this explicit bring-up process. Authentication,
     * interposing, failed insertion and signature policy are untouched.
     */
    if (error == 0 && uap->call == 0x5a && strcmp(target, "AMFI") == 0 &&
        strcmp(p->p_comm, "SpringBoard") == 0) {
        int enabled = 0;
        if (PE_parse_boot_argn("odin-sb-pathvars", &enabled, sizeof(enabled)) && enabled == 1) {
            struct { uint64_t input_flags; user_addr_t output_flags; } args;
            uint64_t flags;
            int diagnostic_error = copyin(uap->arg, &args, sizeof(args));
            if (diagnostic_error == 0) {
                diagnostic_error = copyin(args.output_flags, &flags, sizeof(flags));
            }
            if (diagnostic_error == 0) {
                uint64_t updated = flags | (1ULL << 1);
                diagnostic_error = copyout(&updated, args.output_flags, sizeof(updated));
                printf("odin-sb-dyld: original flags 0x%llx pathvars 0x%llx copyout %d\\n",
                    flags, updated, diagnostic_error);
            } else {
                printf("odin-sb-dyld: policy output read error %d\\n", diagnostic_error);
            }
        }
    }
#endif
\treturn error;'''
after = after[:start] + function.replace(anchor, hook) + after[end:]
for suffix, text in [('before', before), ('after', after)]:
    (out / ('mac_base.' + suffix + '-sb-dyld.c')).write_text(text)
(out / 'host-sb-dyld.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/security/mac_base.c', tofile='b/security/mac_base.c')))
source.write_text(after)
(out / 'host-sb-dyld-receipt.json').write_text(json.dumps(dict(
    default_disabled=True, development_only=True, boot_arg='odin-sb-pathvars=1',
    process='SpringBoard', policy='AMFI', call=0x5a,
    original_policy_checks_preserved=True, original_error_preserved=True,
    flags_added=2, signature_checks_changed=False, device_commands_executed=False,
    before_sha256=hashlib.sha256(before.encode()).hexdigest(),
    after_sha256=hashlib.sha256(after.encode()).hexdigest()), indent=2)+'\n')
print('Installed narrowly gated path-variable bit; original AMFI result retained')
