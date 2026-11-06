"""Guest-side HakiOS physical-timer compatibility port; preserve u71 inputs."""
from pathlib import Path
import difflib, hashlib, json, shutil

ROOT = Path('/home/odin/unixnu-odin-build')
SOURCE = ROOT/'upstream/.cache/xnu-work/osfmk/arm64/machine_routines.c'
OUT = ROOT/'evidence/odin-virtual-timer-u72'
OUT.mkdir(exist_ok=False)
before = SOURCE.read_text()
needle = '\t/* disable the physical timer as a precaution, as its registers reset to architecturally unknown values */\n\t__builtin_arm_wsr64("CNTP_CTL_EL0", CNTP_CTL_EL0_IMASKED);'
assert before.count(needle) == 1
replacement = '''#if defined(APPLE_ARM64_ARCH_FAMILY)
\t/* Apple platforms own their EL1 physical timer. */
\t__builtin_arm_wsr64("CNTP_CTL_EL0", CNTP_CTL_EL0_IMASKED);
#else
\t/* HakiOS port: Qualcomm's hypervisor can trap physical timer accesses.
\t * Retain the virtual timer above; do not touch CNTP_CTL_EL0 at EL1. */
#endif'''
after = before.replace(needle, replacement)
(OUT/'machine_routines.c.before').write_text(before)
(OUT/'machine_routines.c.after').write_text(after)
(OUT/'virtual-timer.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/osfmk/arm64/machine_routines.c', tofile='b/osfmk/arm64/machine_routines.c')))
SOURCE.write_text(after)
obj = ROOT/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/machine_routines.o'
if obj.exists():
    shutil.copy2(obj, OUT/'machine_routines.o.before')
    obj.unlink()
kernel = ROOT/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped'
shutil.copy2(kernel, OUT/'kernel.before.macho')
link = (ROOT/'evidence/odin-vm-progress-u68/link_kernel.sh').read_text()
link = link.replace('evidence/odin-vm-progress-u68', 'evidence/odin-virtual-timer-u72')
(OUT/'link_kernel.sh').write_text(link)
(OUT/'source-verification.json').write_text(json.dumps(dict(
    parent_release='u71', source_sha256=hashlib.sha256(after.encode()).hexdigest(),
    reference='HakiOS xnu/hakios.patch _enable_virtual_timer APPLE_ARM64_ARCH_FAMILY guard',
    second_reference='haydn SM8350 0001-sm8350-el1pcen-physical-timer.patch',
    virtual_timer_kept=True, physical_timer_access_nonapple=False,
    physical_fix_verified=False), indent=2)+'\n')
print('Installed the HakiOS virtual-timer guard; previous source/object/kernel preserved')
