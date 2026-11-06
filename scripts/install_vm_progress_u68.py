"""Guest only: cover the interval after the photographed u67 stage 2F.

This adds observations, not a claimed hardware fix. Before translation-table
takeover only the existing identity framebuffer is used. After arm_vm_init
returns, map the framebuffer with the same cache policy as video_console.c.
Never carry a physical framebuffer pointer across TTBR0 invalidation.
"""
from pathlib import Path
import difflib, hashlib, json, shutil

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT / 'upstream/.cache/xnu-work'
OUT = ROOT / 'evidence/odin-vm-progress-u68'
OUT.mkdir(exist_ok=True)
files = ['osfmk/arm/arm_init.c', 'osfmk/arm64/arm_vm_init.c']
before = {f: (TREE/f).read_text() for f in files}
for f in files:
    shutil.copy2(TREE/f, OUT/(Path(f).name+'.before'))

helper = r'''
/* ODIN_VM_PROGRESS_U68: normal path continues; no custom exception vectors. */
extern void odin_hex_row(unsigned long, unsigned long, unsigned long, boot_args *);
volatile unsigned long odin_postvm_last_stage;
volatile unsigned long odin_postvm_last_caller;
volatile unsigned long odin_postvm_framebuffer;
static boot_args odin_postvm_args;

__attribute__((noinline)) void
odin_postvm_stage(unsigned long stage)
{
    odin_postvm_last_stage = stage;
    odin_postvm_last_caller = (unsigned long)__builtin_return_address(0);
    if (!odin_postvm_framebuffer) return;
    odin_hex_row(stage, 10, 0xc000, &odin_postvm_args);
    odin_hex_row(odin_postvm_last_caller, 11, 0xc001, &odin_postvm_args);
}

static void
odin_postvm_init(boot_args *args)
{
    /* Bounds of this board's framebuffer; no unrelated MMIO is accessed. */
    if (!args->Video.v_baseAddr || args->Video.v_rowBytes != 4320 ||
        args->Video.v_height != 2400 || args->Video.v_width != 1080) return;
    odin_postvm_args = *args;
    odin_postvm_last_stage = 0x40; /* arm_vm_init returned, before IO mapping */
#if HAS_UCNORMAL_MEM
    odin_postvm_framebuffer = ml_io_map_wcomb(args->Video.v_baseAddr, 4320UL * 2400);
#else
    odin_postvm_framebuffer = ml_io_map(args->Video.v_baseAddr, 4320UL * 2400);
#endif
    if (!odin_postvm_framebuffer) return;
    odin_postvm_args.Video.v_baseAddr = odin_postvm_framebuffer;
    odin_postvm_stage(0x41);
}
'''
c = before[files[0]]
anchor = '__startup_func\nvoid\narm_init('
assert c.count(anchor) == 1 and 'ODIN_VM_PROGRESS_U68' not in c
c = c.replace(anchor, helper+'\n'+anchor)
needle = '\tarm_vm_init(xmaxmem, args);'
assert c.count(needle) == 1
c = c.replace(needle, needle+'\n\todin_postvm_init(args);')
stages = {'40': 'arm_vm_init returned; before framebuffer mapping',
          '41': 'post-VM framebuffer IO mapping completed'}
for needle, stage, description in [
    ('\tPE_consistent_debug_inherit();', 0x42, 'consistent debug inheritance returned'),
    ('\tconst unsigned int serial_exists = serial_init();', 0x43, 'serial_init returned'),
    ('\tkernel_startup_initialize_upto(STARTUP_SUB_KPRINTF);', 0x44, 'KPRINTF startup returned'),
    ('\tPE_create_console();', 0x46, 'console and panic-log initialization returned'),
    ('\tPE_init_printf(FALSE);', 0x47, 'PE_init_printf returned'),
    ('\tcpu_machine_idle_init(TRUE);', 0x48, 'cpu_machine_idle_init returned'),
    ('\tPE_init_platform(TRUE, &BootCpuData);', 0x49, 'VM-ready platform initialization returned'),
    ('\tml_map_cpu_pio();', 0x4a, 'CPU PIO mapping returned'),
    ('\tcpu_timebase_init(TRUE);', 0x4b, 'CPU timebase initialization returned'),
    ('\tPE_init_cpu();', 0x4c, 'platform CPU initialization returned'),
    ('\tfiq_context_init(TRUE);', 0x4d, 'FIQ context initialization returned'),
]:
    assert needle in c, needle
    c = c.replace(needle, needle+f'\n\todin_postvm_stage(0x{stage:x});', 1)
    stages[f'{stage:02X}'] = description
c = c.replace('\tPE_create_console();', '\todin_postvm_stage(0x45);\n\tPE_create_console();')
stages['45'] = 'before console initialization'
c = c.replace('\tmachine_startup(args);', '\todin_postvm_stage(0x4e);\n\tmachine_startup(args);', 1)
stages['4E'] = 'before machine_startup'

vm = before[files[1]]
needle = 'void\narm_vm_init(uint64_t memory_size, boot_args * args)'
assert vm.count(needle) == 1
vm = vm.replace(needle, 'extern void odin_platform_stage(boot_args *, unsigned long);\n\n'+needle)
for needle, stage, description in [
    ('\tgVirtBase = args->virtBase;', 0x30, 'arm_vm_init entered'),
    ('\tavail_start = args->topOfKernelData;', 0x31, 'bootstrap memory range calculations complete'),
    ('\tarm_vm_prot_init(args);', 0x32, 'before kernel segment page protections'),
    ('\tva_l1 = va_l2 = LOW_GLOBAL_BASE_ADDRESS;', 0x33, 'kernel segment page protections complete'),
    ('\tarm_vm_physmap_init(args);', 0x34, 'before physical aperture initialization'),
    ('\tset_mmu_ttb_alternate(cpu_ttep & TTBR_BADDR_MASK);', 0x35, 'physical aperture initialized; before TTBR1 replacement'),
]:
    assert vm.count(needle) == 1, needle
    vm = vm.replace(needle, f'\todin_platform_stage(args, 0x{stage:x});\n'+needle)
    stages[f'{stage:02X}'] = description

patch = ''
for rel, after in zip(files, (c, vm)):
    (TREE/rel).write_text(after)
    patch += ''.join(difflib.unified_diff(before[rel].splitlines(True), after.splitlines(True), fromfile='a/'+rel, tofile='b/'+rel))
(OUT/'vm-progress.patch').write_text(patch)
(OUT/'verification.json').write_text(json.dumps(dict(stages=stages,
    no_normal_path_halt=True, normal_exception_vectors_preserved=True,
    physical_framebuffer_access_after_ttbr_switch=False,
    post_vm_framebuffer_mapping='same cache policy as native video_console.c',
    source_sha256={f: hashlib.sha256((TREE/f).read_bytes()).hexdigest() for f in files},
    hardware_fix_claimed=False, device_tested=False), indent=2)+'\n')
print('Installed pre/post-VM observations; normal boot continues unchanged')
