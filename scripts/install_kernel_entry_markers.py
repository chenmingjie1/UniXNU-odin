"""Linux build guest: add diagnostic source checkpoints inside native XNU entry."""
from pathlib import Path
import difflib,hashlib,json,shutil
root=Path('/home/odin/unixnu-odin-build')
source=root/'upstream/.cache/xnu-work/osfmk/arm64/start.s'
out=root/'evidence/odin-entry-u07';out.mkdir(exist_ok=True)
before=source.read_text()
assert 'ODIN_KERNEL_ENTRY_MARK' not in before,'Already applied; do not apply twice'
shutil.copy2(source,out/'start.s.before')
kernel=root/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped'
shutil.copy2(kernel,out/'native-before.macho')
macro=r'''
// ODIN_KERNEL_ENTRY_MARK: diagnostic stores before MMU enable only.
// x0 or x20 points at boot_args. x9-x15 are scratch at these checkpoints.
.macro odin_kernel_mark args, index, lo, hi
 ldr x9, [\args, #0x28]
 cbz x9, 90f
 ldr x10, [\args, #0x38]
 cmp x10, #2304
 b.lo 90f
 ldr x11, [\args, #0x48]
 cmp x11, #64
 b.lo 90f
 mov w12, #\lo
 movk w12, #\hi, lsl #16
 add x13, x9, #((4 + \index) * 256)
 mov x11, #64
91:
 mov x14, x13
 mov x15, #32
92:
 stp w12, w12, [x14], #8
 subs x15, x15, #1
 b.ne 92b
 add x13, x13, x10
 subs x11, x11, #1
 b.ne 91b
 dsb sy
90:
.endm

'''
needle='LEXT(start_first_cpu)'
assert before.count(needle)==1
text=before.replace(needle,macro+needle+'\n\t.globl EXT(odin_entry_mark0)\nLEXT(odin_entry_mark0)\n\todin_kernel_mark x0, 0, 0, 0xffff\n')
start=text.index(needle)
head,body=text[:start],text[start:]
needle='\tmsr\t\tOSLAR_EL1, xzr'
assert body.count(needle)==1
body=body.replace(needle,needle+'\n\t.globl EXT(odin_entry_mark1)\nLEXT(odin_entry_mark1)\n\todin_kernel_mark x0, 1, 0x00ff, 0xffff\n')
for needle,index,lo,hi in [('Lkernelcache_base_found:',2,'0x00ff','0xff00'),('Lbootstrap_tables_ready:',3,'0x8000','0xffff')]:
 assert body.count(needle)==1
 body=body.replace(needle,needle+f'\n\t.globl EXT(odin_entry_mark{index})\nLEXT(odin_entry_mark{index})\n\todin_kernel_mark x20, {index}, {lo}, {hi}\n')
needle='\t// Enable caches, MMU, ROP and JOP'
assert body.count(needle)==1
body=body.replace(needle,'\t.globl EXT(odin_entry_mark4)\nLEXT(odin_entry_mark4)\n\todin_kernel_mark x20, 4, 0x8080, 0xff80\n'+needle)
text=head+body
source.write_text(text)
patch=''.join(difflib.unified_diff(before.splitlines(True),text.splitlines(True),fromfile='a/osfmk/arm64/start.s',tofile='b/osfmk/arm64/start.s'))
(out/'odin-early-entry-markers.patch').write_text(patch)
(out/'verification.json').write_text(json.dumps({'before_sha256':hashlib.sha256(before.encode()).hexdigest(),
 'after_sha256':hashlib.sha256(text.encode()).hexdigest(),'native_before_sha256':hashlib.sha256(kernel.read_bytes()).hexdigest(),
 'checkpoints':['native start_first_cpu entered','OSLAR write returned','boot args loaded and page table pool cleared','bootstrap tables built','before MMU enable'],
 'only_before_mmu':True,'scratch_registers':'x9-x15; x0/boot args and x20-x26/lr preserved','device_tested':False},indent=2)+'\n')
print('Native XNU source checkpoints installed; old kernel and source backed up')
