"""Apply bounded MMU/early-C diagnostics in the isolated Linux kernel tree.

No firmware, system image or phone operations. Requires the u07 source markers.
"""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT / 'upstream/.cache/xnu-work'
OUT = ROOT / 'evidence/odin-mmu-u08'
OUT.mkdir(exist_ok=False)
start = TREE / 'osfmk/arm64/start.s'
cinit = TREE / 'osfmk/arm/arm_init.c'
before = start.read_text()
cbefore = cinit.read_text()
assert 'ODIN_KERNEL_ENTRY_MARK' in before and 'ODIN_MMU_DIAGNOSTICS' not in before
shutil.copy2(start, OUT / 'start.s.before')
shutil.copy2(cinit, OUT / 'arm_init.c.before')
shutil.copy2(ROOT / 'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped', OUT / 'native-before.macho')

# Low reset vectors are not changed. Only the dedicated exception-vector table
# routes to a terminal, stackless handler, with original ESR/ELR/FAR captured.
a = before.index('LEXT(LowExceptionVectorBase)')
b = before.index('#if defined(KERNEL_INTEGRITY_KTRR)', a)
vectors = before[a:b]
assert vectors.count('\tb\t\t.') == 16
text = before[:a] + vectors.replace('\tb\t\t.', '\tb\t\tEXT(odin_early_exception)') + before[b:]

needle = '\tmov\t\tx20, x0\n\tmov\t\tx21, #0'
assert text.count(needle) == 1
text = text.replace(needle, needle + '''
 adrp x9, EXT(odin_diag_bootargs)@page
 add x9, x9, EXT(odin_diag_bootargs)@pageoff
 str x20, [x9]
''')

needle = 'Lbootstrap_tables_ready:\n'
assert text.count(needle) == 1
text = text.replace(needle, needle + r'''
 // Diagnostics accept the measured MIX4 framebuffer only. Refuse a mismatched
 // layout before modifying any descriptors or drawing the register panel.
 ldr x9, [x20, #0x28]
 MOV64 x10, 0xea600000
 cmp x9, x10
 b.ne Lodin_diag_stop
 ldr x10, [x20, #0x38]
 mov x11, #4320
 cmp x10, x11
 b.ne Lodin_diag_stop
 ldr x10, [x20, #0x40]
 cmp x10, #1080
 b.ne Lodin_diag_stop
 ldr x10, [x20, #0x48]
 cmp x10, #2400
 b.ne Lodin_diag_stop
 ldr x10, [x20, #0x50]
 cmp x10, #32
 b.ne Lodin_diag_stop
 // Map only the five 2 MiB framebuffer blocks. Every target leaf must be empty,
 // and its L2 table must lie INSIDE the existing bootstrap allocation pool.
 MOV64 x17, 0xeb000000
Lodin_map_framebuffer:
 and x10, x9, #ARM_TT_L1_INDEX_MASK
 lsr x10, x10, #ARM_TT_L1_SHIFT
 ldr x11, [x25, x10, lsl #3]
 and x10, x11, #3
 cmp x10, #3
 b.ne Lodin_diag_stop
 and x11, x11, #ARM_TTE_TABLE_MASK
 cmp x11, x25
 b.lo Lodin_diag_stop
 add x12, x25, #(BOOTSTRAP_TABLE_BYTES >> 12), lsl #12
 cmp x11, x12
 b.hs Lodin_diag_stop
 and x10, x9, #ARM_TT_L2_INDEX_MASK
 lsr x10, x10, #ARM_TT_L2_SHIFT
 add x11, x11, x10, lsl #3
 ldr x12, [x11]
 cbnz x12, Lodin_diag_stop
 and x12, x9, #ARM_TTE_BLOCK_L2_MASK
 mov x13, #(ARM_TTE_BOOT_BLOCK | ARM_TTE_BLOCK_ATTRINDX(CACHE_ATTRINDX_WRITECOMB))
 orr x12, x12, x13
 str x12, [x11]
 add x9, x9, #0x200, lsl #12
 cmp x9, x17
 b.lo Lodin_map_framebuffer
 dsb sy
''')
# fb start is 2 MiB aligned. Its byte extent is 10,368,000 and ends below eb000000.
assert 0xea600000 % 0x200000 == 0 and 0xea600000 + 4320 * 2400 <= 0xeb000000

needle = '\t.globl EXT(odin_entry_mark4)'
assert text.count(needle) == 1
text = text.replace(needle, r'''
 // Keep an identity-mapped, stackless exception path while changing SCTLR.
 mrs x0, VBAR_EL1
 adrp x9, EXT(odin_diag_saved_vbar)@page
 add x9, x9, EXT(odin_diag_saved_vbar)@pageoff
 str x0, [x9]
 adrp x0, EXT(LowExceptionVectorBase)@page
 add x0, x0, EXT(LowExceptionVectorBase)@pageoff
 msr VBAR_EL1, x0
 isb
 odin_hex_sysreg MIDR_EL1, 0, 0xa000
 odin_hex_sysreg ID_AA64MMFR0_EL1, 1, 0xa001
 odin_hex_sysreg ID_AA64MMFR1_EL1, 2, 0xa002
 odin_hex_sysreg TCR_EL1, 3, 0xa003
 odin_hex_sysreg SCTLR_EL1, 4, 0xa004
 odin_hex_sysreg TTBR0_EL1, 5, 0xa005
 odin_hex_sysreg TTBR1_EL1, 6, 0xa006
 odin_hex_sysreg MAIR_EL1, 7, 0xa007
''' + needle)
needle = '\tMSR_SCTLR_EL1_X0\n\tisb\t\tsy\n'
assert text.count(needle) == 1
text = text.replace(needle, needle + '''
 .globl EXT(odin_entry_mark5)
LEXT(odin_entry_mark5)
 odin_kernel_mark x20, 5, 0x80ff, 0xff00
''')
needle = '\t// Return to arm_init()\n\tret'
assert text.count(needle) == 1
text = text.replace(needle, '''
 .globl EXT(odin_entry_mark6)
LEXT(odin_entry_mark6)
 odin_kernel_mark x20, 6, 0x00ff, 0xff80
''' + needle)
helper = Path(__file__).with_name('odin_mmu_diagnostics.S.inc').read_text()
# Insert after the existing marker macro so helper entrypoints can use it.
needle = '\nLEXT(start_first_cpu)'
assert text.count(needle) == 1
text = text.replace(needle, '\n' + helper + needle)

# C callbacks operate through the normal C ABI; they do not assume a compiler
# register still holds boot_args, and leave callee-saved registers untouched.
ctext = cbefore
needle = '__startup_func\nvoid\narm_init('
assert ctext.count(needle) == 1
ctext = ctext.replace(needle, '''extern void odin_c_entry(boot_args *);
extern void odin_c_presign(boot_args *);
extern void odin_c_rebase(boot_args *);
extern void odin_c_cpudata(boot_args *);
extern void odin_c_platform(boot_args *);

''' + needle)
for needle, replacement in [
    ('\tarm_setup_pre_sign();', '\todin_c_entry(args);\n\tarm_setup_pre_sign();\n\todin_c_presign(args);'),
    ('\tarm_slide_rebase_and_sign_image();', '\tarm_slide_rebase_and_sign_image();\n\todin_c_rebase(args);'),
    ('\tcpu_data_init(&BootCpuData);', '\tcpu_data_init(&BootCpuData);\n\todin_c_cpudata(args);'),
    ('\tPE_init_platform(FALSE, args);', '\todin_c_platform(args);\n\tPE_init_platform(FALSE, args);'),
]:
    # Restrict replacements to cold arm_init; other functions share these calls.
    a = ctext.index('void\narm_init(')
    head, body = ctext[:a], ctext[a:]
    assert needle in body
    ctext = head + body.replace(needle, replacement, 1)

start.write_text(text)
cinit.write_text(ctext)
patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True), fromfile='a/osfmk/arm64/start.s', tofile='b/osfmk/arm64/start.s'))
patch += ''.join(difflib.unified_diff(cbefore.splitlines(True), ctext.splitlines(True), fromfile='a/osfmk/arm/arm_init.c', tofile='b/osfmk/arm/arm_init.c'))
(OUT / 'odin-mmu-diagnostics.patch').write_text(patch)
(OUT / 'verification.json').write_text(json.dumps({
    'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
    'c_source_sha256': hashlib.sha256(ctext.encode()).hexdigest(),
    'framebuffer': {'physical_base': '0xea600000', 'bytes': 10368000, 'mapping_end': '0xeb000000', 'mapping_bytes': 10485760, 'normal_non_cacheable': True},
    'existing_mapping_overwrite_allowed': False,
    'early_exception_fields': ['ESR_EL1', 'ELR_EL1', 'FAR_EL1', 'SCTLR_EL1', 'SPSR_EL1', 'TCR_EL1'],
    'normal_exception_vectors_restored_before': 'PE_init_platform',
    'kernel_recompiled': False, 'device_tested': False,
}, indent=2) + '\n')
print('MMU/early-C diagnostics installed with source backups; rebuild required')
