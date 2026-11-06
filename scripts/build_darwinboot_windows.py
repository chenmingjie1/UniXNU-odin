"""Build the pinned DarwinBoot with measured Mu headers/libraries on Windows.

This produces a real ARM64 UEFI driver, not a phone boot image. The explicit
constructor entry substitutes for generated EDK2 glue; driver logic is intact.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess
import shutil
ROOT=Path(__file__).resolve().parents[3]
DEVICE=ROOT/'work/UniXNU-odin'
MU=ROOT/'work/Mu-Silicium-odin'
UP=ROOT/'work/UniXNU-source/UniXNU-04573c510c5fd4892ca6948739389141cc9e05f5'
SOURCE=ROOT/'work/UniXNU-components/DarwinBoot-3c75734014cdab0acd9541e88057b7606ee7ae08'
BIN=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
BUILD=MU/'Build/odinPkg/RELEASE_CLANGPDB/AARCH64'
OLD=BUILD/'SiliciumPkg/Applications/UFPLoader/UFPLoader'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='')
parser.add_argument('--desktop-media', action='store_true')
parser.add_argument('--touch-power', action='store_true', help='Verified MIX4 firmware touch rail/reset preparation')
parser.add_argument('--resident-core7', action='store_true', help='Keep BSP firmware resident; use proven odin PSCI core7 handoff')
options=parser.parse_args()
assert not options.tag or options.tag.isalnum()
assert not options.desktop_media or options.tag, 'Desktop changes require an isolated tagged output'
assert not options.resident_core7 or (options.desktop_media and options.tag)
OUT=DEVICE/('build/darwinboot-'+options.tag if options.tag else 'build/darwinboot')
OUT.mkdir(parents=True,exist_ok=True)
commands=[]

def run(command):
    commands.append(list(map(str,command)))
    p=subprocess.run(command,capture_output=True,text=True)
    with (OUT/'build.log').open('a',encoding='utf-8') as f:
        f.write(p.stdout+p.stderr)
    (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    if p.returncode: raise SystemExit(p.stdout+p.stderr)

# Match the same Mu headers and archive PCDs. Omit unrelated application glue.
autogen=(OLD/'DEBUG/AutoGen.c').read_text()
cut=autogen.index('EFI_STATUS\nEFIAPI\nUefiBootServicesTableLibConstructor')
autogen=autogen[:cut]
autogen += '''
EFI_GUID gUniXNULoaderProtocolGuid = {0x0f0a492e,0x5a6a,0x49f6,{0xa1,0xbf,0x74,0x3c,0x87,0xab,0x1c,0xfe}};
EFI_GUID gEfiFileInfoGuid = EFI_FILE_INFO_ID;
EFI_STATUS EFIAPI UefiBootServicesTableLibConstructor(EFI_HANDLE,EFI_SYSTEM_TABLE*);
EFI_STATUS EFIAPI UefiRuntimeServicesTableLibConstructor(EFI_HANDLE,EFI_SYSTEM_TABLE*);
EFI_STATUS EFIAPI UefiLibConstructor(EFI_HANDLE,EFI_SYSTEM_TABLE*);
EFI_STATUS EFIAPI DarwinBootEntry(EFI_HANDLE,EFI_SYSTEM_TABLE*);
EFI_STATUS EFIAPI OdinEntry(EFI_HANDLE h,EFI_SYSTEM_TABLE *s) {
  EFI_STATUS status;
  status=UefiBootServicesTableLibConstructor(h,s); if(EFI_ERROR(status))return status;
  status=UefiRuntimeServicesTableLibConstructor(h,s); if(EFI_ERROR(status))return status;
  status=UefiLibConstructor(h,s); if(EFI_ERROR(status))return status;
  return DarwinBootEntry(h,s);
}
'''
autogen=autogen.replace('#include <Uefi.h>','#include <Uefi.h>\n#include <Guid/FileInfo.h>',1)
(OUT/'OdinEntry.c').write_text(autogen)
# The upstream assembly only uses ASM_FUNC. COFF uses its own section flags.
(OUT/'AsmMacroLib.h').write_text('#define ASM_FUNC(Name) .text ; .globl Name ; .p2align 2 ; Name:\n')
headers=[OUT,MU/'Mu_Basecore/MdePkg/Include',MU/'Mu_Basecore/MdePkg/Include/AArch64',UP/'package/UniXNUPkg/Include']
flags=['--target=aarch64-pc-windows-msvc','-ffreestanding','-fshort-wchar','-fno-builtin',
       '-fno-stack-protector','-mno-stack-arg-probe','-fno-asynchronous-unwind-tables','-Oz',
       '-DNDEBUG','-DMDEPKG_NDEBUG','-D_EFI_AARCH64_']
includes=[v for p in headers for v in ['-I',str(p)]]
(OUT/'build.log').write_text('')
objects=[]
# Keep the pinned component archive immutable. XNU 8796's actual boot.h has
# a 608-byte command line (boot_args is 0x2e0), unlike Darwin 23's 1024 bytes.
staged=OUT/'source';staged.mkdir(exist_ok=True)
for original in (SOURCE/'DarwinBootPkg/Driver').iterdir():
    if original.suffix in ('.c','.h','.S'): shutil.copy2(original,staged/original.name)
header=(staged/'BootArgs.h').read_text()
assert 'CommandLine[1024]' in header and '== 0x480' in header
header=header.replace('Darwin 23 pexpert/pexpert/arm64/boot.h ABI','XNU 8796.101.5 pexpert/pexpert/arm64/boot.h ABI')
header=header.replace('CommandLine[1024]','CommandLine[608]').replace('== 0x478','== 0x2d8').replace('== 0x480','== 0x2e0')
(staged/'BootArgs.h').write_text(header)
source=(staged/'DarwinBoot.c').read_text()
assert source.count('CommandLine[1024]')==1
source=source.replace('CommandLine[1024]','CommandLine[sizeof (((DARWIN_BOOT_ARGS *)0)->CommandLine)]')
source=source.replace('UINT64 VideoBase, UINT64 VideoBytes);','UINT64 VideoBase, UINT64 VideoBytes, UINT64 VideoRowBytes);')
source=source.replace('  CopyMem (Args->Video, Video, sizeof (Video));',
 '  CopyMem (Args->Video, Video, sizeof (Video));\n  Args->Video[1] = 0; // diagnostic text console, no graphics boot screen')
source=source.replace('WindowSize, Video[0], Video[2] * Video[4]);',
 'WindowSize, (Video[3] >= 256 && Video[4] >= 64 && Video[5] == 32) ? Video[0] : 0, Video[2] * Video[4], Video[2]);')
(staged/'DarwinBoot.c').write_text(source)
if options.desktop_media:
    from stage_darwinboot_desktop_media import stage_desktop_media
    stage_desktop_media(staged)
(staged/'Entry.S').write_bytes(Path(__file__).with_name('OdinDarwinEnter.S').read_bytes())
sources=[staged/'DarwinBoot.c',staged/'Entry.S',OUT/'OdinEntry.c']
if options.resident_core7:
    from stage_darwinboot_resident import stage_resident
    sources += stage_resident(staged)
    if options.touch_power:
        for name in ('OdinTouchPower.h','OdinTouchRpmhFingerprint.h'):
            shutil.copy2(DEVICE/'firmware'/name,staged/name)
        p=staged/'OdinResident.c';text=p.read_text()
        text=text.replace('#include "OdinResident.h"','#include "OdinResident.h"\n#include "OdinTouchPower.h"')
        anchor=' Status=gBS->AllocatePages(AllocateAnyPages,EfiLoaderData,4,&Stack);'
        assert text.count(anchor)==1
        text=text.replace(anchor,' Status=OdinTouchPowerPrepare();\n Print(L"MIX4 touch preparation: %r\\r\\n",Status);\n'+anchor)
        p.write_text(text)
for source in sources:
    obj=OUT/(source.stem+'.obj')
    run([BIN/'clang.exe',*flags,*includes,'-c',source,'-o',obj])
    objects.append(obj)
libraries=[]
for line in (OLD/'OUTPUT/static_library_files.lst').read_text().splitlines():
    p=Path(line.strip())
    if p.name in ('UFPLoader.lib','UefiApplicationEntryPoint.lib'):continue
    if not p.is_file():raise SystemExit('Missing measured Mu archive: '+str(p))
    libraries.append(p)
efi=OUT/'DarwinBoot.efi'
run([BIN/'lld-link.exe','/nodefaultlib','/entry:OdinEntry','/subsystem:efi_boot_service_driver',
     '/dll','/machine:arm64','/base:0','/align:4096','/timestamp:0','/out:'+str(efi),
     '/map:'+str(OUT/'DarwinBoot.map'),*objects,*libraries])
data=efi.read_bytes()
pe=int.from_bytes(data[0x3c:0x40],'little')
assert data[pe:pe+4]==b'PE\0\0'
assert int.from_bytes(data[pe+4:pe+6],'little')==0xaa64
assert int.from_bytes(data[pe+24+68:pe+24+70],'little')==11
record={'artifact':str(efi),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
        'source_revision':'3c75734014cdab0acd9541e88057b7606ee7ae08',
        'arm64_pe_verified':True,'efi_boot_service_driver':True,'device_tested':False,
        'phone_boot_image':False,'libraries':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in libraries]}
record['boot_args_abi']={'kernel':'8796.101.5','command_line_bytes':608,'structure_bytes':0x2e0,'actual_memory_offset':0x2d8}
record['desktop_media_sidecar']=options.desktop_media
record['resident_core7']=options.resident_core7
record['odin_touch_power']=options.touch_power
record['staged_sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in staged.iterdir() if p.is_file()}
(OUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='libraries'},indent=2))
