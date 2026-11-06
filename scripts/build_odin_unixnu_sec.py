"""Preserve the Android FDT x0 in the standard Mu entry-argument HOB."""
from pathlib import Path
import runpy,subprocess,hashlib,json
# Reuse the measured make-variable resolver and build paths.
c=runpy.run_path(str(Path(__file__).with_name('build_odin_unixnu_bds.py')))
ROOT,MU,BASE,BIN,BT=[c[k] for k in ('ROOT','MU','BASE','BIN','BT')]
SEC=BASE/'SiliciumPkg/Sec/Sec';src=MU/'Silicon/Silicium/SiliciumPkg/Sec'
OUT=ROOT/'work/UniXNU-odin/build/odin-unixnu-sec';OUT.mkdir(parents=True,exist_ok=True)
v=c['variables'](SEC/'GNUmakefile');commands=[]
def run(cmd):
 commands.append(list(map(str,cmd)));p=subprocess.run(cmd,capture_output=True,text=True)
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 with (OUT/'build.log').open('a') as f:f.write(p.stdout+p.stderr)
 if p.returncode:raise SystemExit((p.stdout+p.stderr)[-5000:])
 return p.stdout
(OUT/'build.log').write_text('')
text=(src/'Sec.c').read_text()
text=text.replace('SecMain (VOID)','SecMain (UINT64 EntryArg)').replace('SecEntry (VOID)','SecEntry (UINT64 EntryArg)').replace('SecMain ();','SecMain (EntryArg);')
needle='  ODIN_CHECKPOINT (5);'
assert text.count(needle)==1
text=text.replace(needle,'''  // Android's incoming x0 points to the firmware FDT. Its initrd is in
  // odin's existing reserved Kernel region, not the DXE allocation heap.
  STATIC CONST EFI_GUID EntryArgHob = {0xdaee82e6,0x8090,0x4e72,{0xbf,0xb9,0x78,0xc1,0x3c,0xd4,0xe3,0x59}};
  BuildGuidDataHob (&EntryArgHob, &EntryArg, sizeof (EntryArg));
'''+needle)
(OUT/'Sec.c').write_text(text)
assembly=(src/'AArch64/ModuleEntryPoint.S').read_text()
needle='ASM_FUNC (_ModuleEntryPoint)'
assert assembly.count(needle)==1
assembly=assembly.replace(needle,needle+'\n  mov x28, x0 // preserve FDT across ABI-conforming setup calls\n')
assembly=assembly.replace('ldr   x0, =ASM_PFX (SecEntry)','ldr   x16, =ASM_PFX (SecEntry)\n  mov   x0, x28')
assembly=assembly.replace('blr   x0','blr   x16')
(OUT/'ModuleEntryPoint.S').write_text(assembly)
run([BIN/'clang.exe',*v['CC_FLAGS'].split(),*v['INC'].split(),'-c',OUT/'Sec.c','-o',OUT/'Sec.obj'])
# Use the exact EDK2 Trim-generated assembly of the measured SEC; its
# preprocessing strips C declarations that raw clang -E would retain.
pre=(SEC/'OUTPUT/AArch64/ModuleEntryPoint.iiii').read_text()
needle='_ModuleEntryPoint: ;'
assert pre.count(needle)==1
pre=pre.replace(needle,needle+'\n  mov x28, x0\n')
assert pre.count('ldr x0, =SecEntry')==1
pre=pre.replace('ldr x0, =SecEntry','ldr x16, =SecEntry\n  mov x0, x28').replace('blr x0','blr x16')
# EDK2's ASM_FUNC emits ELF section flags; use the COFF text section.
pre=pre.replace('.section ".text", "ax"','.text')
(OUT/'ModuleEntryPoint.i').write_text(pre)
run([BIN/'clang.exe',*v['ASM_FLAGS'].split(),'-o',OUT/'ModuleEntryPoint.obj',OUT/'ModuleEntryPoint.i'])
objects=[Path(p) for p in (SEC/'OUTPUT/object_files.lst').read_text().splitlines()]
objects=[OUT/p.name if p.name in ('Sec.obj','ModuleEntryPoint.obj') else p for p in objects]
lib=OUT/'Sec.lib';lib.unlink(missing_ok=True);run([BIN/'llvm-ar.exe','rcs',lib,*objects])
libs=[Path(p) for p in (SEC/'OUTPUT/static_library_files.lst').read_text().splitlines()]
libs=[lib if p.name=='Sec.lib' else p for p in libs]
run([BIN/'lld-link.exe',*v['DLINK_FLAGS'].split(),'/OUT:'+str(OUT/'Sec.dll'),*libs])
run([BT/'GenFw.exe','-e','SEC','-o',OUT/'Sec.efi',OUT/'Sec.dll'])
# This SEC executes in place. Relocate before stripping; GenFv cannot fix
# absolute pointers after the relocation directory has been discarded.
run([BT/'GenFw.exe','--rebase','0x9fd00000','-o',OUT/'Sec.rebased',OUT/'Sec.efi'])
run([BT/'GenFw.exe','-l','-o',OUT/'Sec.stripped',OUT/'Sec.rebased'])
run([BT/'GenFw.exe','-t','-o',OUT/'Sec.te',OUT/'Sec.stripped'])
record={'scope':'New SEC FDT HOB path; pending device validation','shared_sources_modified':False,
 'sec_te_sha256':hashlib.sha256((OUT/'Sec.te').read_bytes()).hexdigest(),
 'original_sources':{str(p.relative_to(MU)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (src/'Sec.c',src/'AArch64/ModuleEntryPoint.S')},
 'new_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'Sec.c',OUT/'ModuleEntryPoint.S')}}
(OUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(record)
