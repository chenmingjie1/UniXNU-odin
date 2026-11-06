"""Install the missing HakiOS exec handoff in the build VM, never on a phone.

Based on hakios-xnu-kernel 88513176b1e96ecf0b764cd62c6f4e6ac71345e3,
xnu/hakios.patch (MIT). Restricted to a DEVELOPMENT opt-in and SpringBoard.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', required=True)
a = p.parse_args()
assert a.tag.isalnum()
base = Path('/home/odin/unixnu-odin-build')
out = base / ('evidence/odin-display-owner-' + a.tag)
out.mkdir(parents=True, exist_ok=True)
source = base / 'upstream/.cache/xnu-work/bsd/kern/kern_exec.c'
before = source.read_text()
assert 'ODIN_SB_EXEC_U60' not in before, 'Preserve installed handoff'
anchor = '__attribute__((noinline))\nstatic int\nexec_extract_strings(struct image_params *imgp)'
assert before.count(anchor) == 1
helper = '''/* ODIN_SB_EXEC_U60: fixed library, opt-in computer bring-up only.
 * launchd strips DYLD_ variables from jobs; insert after extracting envv,
 * as in HakiOS exec_inject_env, including pointer/argument accounting.
 */
#if DEBUG || DEVELOPMENT
static TUNABLE(int, odin_sb_ui, "odin-sb-ui", 0);
static bool
odin_sb_exec_env(struct image_params *imgp)
{
    const char *name;
    if (odin_sb_ui != 1 || imgp->ip_ndp == NULL) {
        return false;
    }
    name = imgp->ip_ndp->ni_cnd.cn_nameptr;
    return name != NULL && imgp->ip_ndp->ni_cnd.cn_namelen == 11 &&
        strncmp(name, "SpringBoard", 11) == 0;
}
#endif

'''
after = before.replace(anchor, helper + anchor)
anchor = '\t/* Save space for envv[] NULL terminator */'
assert after.count(anchor) == 1
hook = '''#if DEBUG || DEVELOPMENT
    if (odin_sb_exec_env(imgp)) {
        error = exec_add_user_string(imgp,
            CAST_USER_ADDR_T("DYLD_INSERT_LIBRARIES=/redwood/host-input/libodin-ui-unlock.dylib"),
            UIO_SYSSPACE, TRUE);
        if (error) {
            goto bad;
        }
        if (imgp->ip_argspace < new_ptr_size) {
            error = E2BIG;
            goto bad;
        }
        imgp->ip_argspace -= new_ptr_size;
        imgp->ip_envc++;
        printf("odin-sb-exec: fixed signed UI component environment added\\n");
    }
#endif

'''
after = after.replace(anchor, hook + anchor)
(out / 'kern_exec.before-sb-exec.c').write_text(before)
(out / 'kern_exec.after-sb-exec.c').write_text(after)
(out / 'host-sb-exec.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/bsd/kern/kern_exec.c', tofile='b/bsd/kern/kern_exec.c')))
source.write_text(after)
(out / 'host-sb-exec-receipt.json').write_text(json.dumps(dict(
    upstream_commit='88513176b1e96ecf0b764cd62c6f4e6ac71345e3',
    upstream_file='xnu/hakios.patch', default_disabled=True,
    development_only=True, target_basename='SpringBoard',
    library='/redwood/host-input/libodin-ui-unlock.dylib',
    policy_checks_changed=False, device_commands_executed=False,
    before_sha256=hashlib.sha256(before.encode()).hexdigest(),
    after_sha256=hashlib.sha256(after.encode()).hexdigest()), indent=2)+'\n')
print('Installed development-only SpringBoard exec handoff; source and patch preserved')
