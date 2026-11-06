"""Guest-only: continuous checkpoints and exceptions until arm_vm_init.

No diagnostic halt on a successful path. Low framebuffer identity mapping is
used only while the bootstrap tables own TTBR0. Normal vectors are restored
before arm_vm_init can replace these tables. Existing desktop changes survive.
"""
from pathlib import Path
import difflib, hashlib, json, shutil

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT / 'upstream/.cache/xnu-work'
OUT = ROOT / 'evidence/odin-platform-u66'
OUT.mkdir(exist_ok=False)
files = ['osfmk/arm64/start.s', 'osfmk/arm/arm_init.c', 'pexpert/arm/pe_init.c']
before = {f:(TREE/f).read_text() for f in files}
for f in files:
    shutil.copy2(TREE/f, OUT/(Path(f).name+'.before'))
kernel = ROOT/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped'
shutil.copy2(kernel, OUT/'kernel-before.macho')
assert 'odin_platform_stage' not in before[files[0]]

assembly = r'''
// ODIN_PLATFORM_PROGRESS_U66: normal C ABI, only before arm_vm_init.
// x0=boot_args, x1=stage. Preserve the original LR as on-screen B001.
.p2align 2
.globl EXT(odin_platform_stage)
LEXT(odin_platform_stage)
 stp x19, x20, [sp, #-32]!
 stp x21, lr, [sp, #16]
 mov x19, x0
 mov x20, x1
 mov x21, lr
 adrp x9, EXT(odin_platform_last_stage)@page
 add x9, x9, EXT(odin_platform_last_stage)@pageoff
 str x20, [x9]
 // Known physical phone only: QEMU can continue without writing alien RAM.
 ldr x9, [x19, #0x28]
 MOV64 x10, 0xea600000
 cmp x9, x10
 b.ne 1f
 ldr x9, [x19, #0x38]
 mov x10, #4320
 cmp x9, x10
 b.ne 1f
 mov x0, x20
 mov x1, #8
 mov x2, #0xb000
 mov x3, x19
 bl EXT(odin_hex_row)
 mov x0, x21
 mov x1, #9
 mov x2, #0xb001
 mov x3, x19
 bl EXT(odin_hex_row)
1:
 ldp x21, lr, [sp, #16]
 ldp x19, x20, [sp], #32
 ret

// A dedicated KVA vector table keeps MMU enabled. The older low-address
// terminal handler was only valid during the identity-mapped MMU transition.
.p2align 11
.globl EXT(odin_platform_vectors)
LEXT(odin_platform_vectors)
.rept 16
 b EXT(odin_platform_exception)
 .space 124
.endr
.p2align 2
.globl EXT(odin_platform_exception)
LEXT(odin_platform_exception)
 msr DAIFSet, #15
 mrs x19, ESR_EL1
 mrs x21, ELR_EL1
 mrs x22, FAR_EL1
 mrs x23, SCTLR_EL1
 mrs x24, SPSR_EL1
 mrs x25, TCR_EL1
 adrp x9, EXT(odin_diag_bootargs)@page
 add x9, x9, EXT(odin_diag_bootargs)@pageoff
 ldr x20, [x9]
 cbz x20, Lodin_platform_exception_stop
 // x20 is the original physical boot_args, retained by bootstrap TTBR0.
 mov x0, x19
 mov x1, #10
 mov x2, #0xe000
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x21
 mov x1, #11
 mov x2, #0xe001
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x22
 mov x1, #12
 mov x2, #0xe002
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x23
 mov x1, #13
 mov x2, #0xe003
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x24
 mov x1, #14
 mov x2, #0xe004
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x25
 mov x1, #15
 mov x2, #0xe005
 mov x3, x20
 bl EXT(odin_hex_row)
Lodin_platform_exception_stop:
 b Lodin_platform_exception_stop

.globl EXT(odin_platform_vectors_restore)
LEXT(odin_platform_vectors_restore)
 adrp x9, EXT(odin_diag_saved_vbar)@page
 add x9, x9, EXT(odin_diag_saved_vbar)@pageoff
 ldr x9, [x9]
 msr VBAR_EL1, x9
 isb
 ret
.data
.p2align 3
.globl EXT(odin_platform_last_stage)
LEXT(odin_platform_last_stage)
 .quad 0
.text
'''
start = before[files[0]]
needle = ' adrp x9, EXT(odin_diag_saved_vbar)@page\n add x9, x9, EXT(odin_diag_saved_vbar)@pageoff\n ldr x9, [x9]\n msr VBAR_EL1, x9\n isb\n ret'
assert start.count(needle) == 1
start = start.replace(needle, ' adrp x9, EXT(odin_platform_vectors)@page\n add x9, x9, EXT(odin_platform_vectors)@pageoff\n msr VBAR_EL1, x9\n isb\n ret')
start = start.replace('// Restore Apple\'s normal KVA exception vectors before platform init.',
    '// Use diagnostic KVA vectors during early platform init; restore before VM takeover.')
anchor = '\nLEXT(start_first_cpu)'
assert start.count(anchor) == 1
start = start.replace(anchor, '\n'+assembly+anchor)

cinit = before[files[1]]
needle = 'extern void odin_c_platform(boot_args *);'
assert cinit.count(needle) == 1
cinit = cinit.replace(needle, needle+'\nextern void odin_platform_stage(boot_args *, unsigned long);\nextern void odin_platform_vectors_restore(void);')
stages = {}
replacements = [
 ('\tPE_init_platform(FALSE, args); /* Get platform expert set up */',0x20,'PE_init_platform returned'),
 ('\tboot_progress_init();',0x21,'boot_progress_init returned'),
 ('\tconfigure_timer_apple_regs();',0x22,'configure_timer_apple_regs returned'),
 ('\twfe_timeout_configure();',0x23,'wfe_timeout_configure returned'),
 ('\twfe_timeout_init();',0x24,'wfe_timeout_init returned'),
 ('\tconfigure_misc_apple_regs();',0x25,'configure_misc_apple_regs returned'),
 ('\tml_parse_cpu_topology();',0x27,'ml_parse_cpu_topology returned'),
 ('\tthread = thread_bootstrap();',0x28,'thread_bootstrap returned'),
 ('\tcpu_bootstrap();',0x29,'cpu_bootstrap returned'),
 ('\trtclock_early_init();',0x2a,'rtclock_early_init returned'),
 ('\tkernel_startup_bootstrap();',0x2b,'kernel_startup_bootstrap returned'),
 ('\ttimer_call_init();',0x2c,'timer_call_init returned'),
 ('\tcpu_init();',0x2d,'cpu_init returned'),
 ('\tprocessor_bootstrap();',0x2e,'processor_bootstrap returned'),
]
a = cinit.index('void\narm_init(')
head, body = cinit[:a], cinit[a:]
for needle, stage, description in replacements:
    assert needle in body, needle
    body = body.replace(needle, needle+f'\n\todin_platform_stage(args, 0x{stage:x});', 1)
    stages[f'{stage:02X}'] = description
needle = '\tml_parse_cpu_topology();'
body = body.replace(needle, '\todin_platform_stage(args, 0x26);\n'+needle, 1)
stages['26'] = 'before ml_parse_cpu_topology'
needle = '\tarm_vm_init(xmaxmem, args);'
assert body.count(needle) == 1
body = body.replace(needle, '\todin_platform_stage(args, 0x2f);\n\todin_platform_vectors_restore();\n'+needle)
stages['2F'] = 'before arm_vm_init; last framebuffer-identity diagnostic; normal VBAR restored'
cinit = head+body

pe = before[files[2]]
needle = 'void\nPE_init_platform(boolean_t vm_initialized, void *args)'
assert pe.count(needle) == 1
pe = pe.replace(needle, 'extern void odin_platform_stage(boot_args *, unsigned long);\n\n'+needle)
a = pe.index(needle)
b = pe.index('\nvoid\nPE_create_console', a)
head, body, tail = pe[:a], pe[a:b], pe[b:]
needle = '\tboot_args      *boot_args_ptr = (boot_args *) args;'
assert body.count(needle) == 1
body = body.replace(needle, needle+'\n\tif (!vm_initialized) odin_platform_stage(boot_args_ptr, 0x10);')
stages['10'] = 'PE_init_platform(FALSE) entered'
for needle, stage, description in [
 ('\t\tSecureDTInit(PE_state.deviceTreeHead, PE_state.deviceTreeSize);',0x12,'SecureDTInit returned'),
 ('\t\tpe_identify_machine(boot_args_ptr);',0x13,'pe_identify_machine returned'),
 ('\t\tpe_init_debug();',0x15,'pe_init_debug returned'),
]:
    assert body.count(needle) == 1
    body = body.replace(needle, needle+f'\n\t\todin_platform_stage(boot_args_ptr, 0x{stage:x});')
    stages[f'{stage:02X}'] = description
needle = '\t\tSecureDTInit(PE_state.deviceTreeHead, PE_state.deviceTreeSize);'
body = body.replace(needle, '\t\todin_platform_stage(boot_args_ptr, 0x11);\n'+needle)
stages['11'] = 'PE_state initialized; before SecureDTInit'
needle = '\t\tpe_init_debug();'
body = body.replace(needle, '\t\todin_platform_stage(boot_args_ptr, 0x14);\n'+needle)
stages['14'] = 'platform properties copied; before pe_init_debug'
pe = head+body+tail

patch = ''
for rel, after in zip(files, (start, cinit, pe)):
    (TREE/rel).write_text(after)
    patch += ''.join(difflib.unified_diff(before[rel].splitlines(True), after.splitlines(True), fromfile='a/'+rel, tofile='b/'+rel))
(OUT/'platform-progress.patch').write_text(patch)
(OUT/'verification.json').write_text(json.dumps(dict(stages=stages,
    successful_path_halts=False, diagnostic_vector_scope='odin_c_platform to before arm_vm_init',
    framebuffer_writes_after_vm_takeover=False, original_desktop_archive_reused=True,
    source_sha256={f:hashlib.sha256((TREE/f).read_bytes()).hexdigest() for f in files},
    compiled=False, device_tested=False), indent=2)+'\n')
print('Installed continuous platform progress and KVA exception capture; no phone operations')
