"""Relink measured Mu BDS with a source-built UniXNU handoff.

All new outputs live in the device build directory. Shared Mu sources and
build outputs are read only. Reuse the measured platform library objects,
replace only its old diagnostic/reset hook, and relink the original BDS.
"""
from pathlib import Path
import argparse,re,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[3];MU=ROOT/'work/Mu-Silicium-odin'
BASE=MU/'Build/odinPkg/RELEASE_CLANGPDB/AARCH64'
BM=BASE/'odinPkg/Library/BootManagerLib/BootManagerLib'
BDS=BASE/'MdeModulePkg/Universal/BdsDxe/BdsDxe'
BIN=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
BT=MU/'Mu_Basecore/BaseTools/Bin/Mu-Basetools_extdep/Windows-x86'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--remote-media',action='store_true')
parser.add_argument('--tag',default='')
parser.add_argument('--remote-tag',default='u64')
parser.add_argument('--resident-core7',action='store_true')
parser.add_argument('--kernel-readback',action='store_true')
options=parser.parse_args()
assert (not options.tag or options.tag.isalnum()) and options.remote_tag.isalnum()
assert not options.resident_core7 or (options.remote_media and options.tag)
OUT=ROOT/('work/UniXNU-odin/build/odin-unixnu-bds-u65' if options.remote_media else 'work/UniXNU-odin/build/odin-unixnu-bds');OUT.mkdir(parents=True,exist_ok=True)
if options.tag:
 OUT=ROOT/('work/UniXNU-odin/build/odin-unixnu-bds-'+options.tag);OUT.mkdir(parents=True,exist_ok=True)
commands=[]
def run(cmd):
 commands.append(list(map(str,cmd)));p=subprocess.run(cmd,capture_output=True,text=True)
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 with (OUT/'build.log').open('a') as f:f.write(p.stdout+p.stderr)
 if p.returncode:raise SystemExit(p.stdout+p.stderr)
def variables(path):
 text=path.read_text().replace('\\\n',' ')
 values={m[1]:m[2].strip() for m in re.finditer(r'^([A-Za-z_][\w]*)\s*=\s*(.*)$',text,re.M)}
 values['WORKSPACE']=str(MU)
 def expand(text):
  for _ in range(30):
   new=re.sub(r'\$\((\w+)\)',lambda m:values.get(m[1],m[0]),text)
   if new==text:return text
   text=new
  raise ValueError('Recursive make variable')
 return {k:expand(v) for k,v in values.items()}
v=variables(BM/'GNUmakefile');d=variables(BDS/'GNUmakefile')
source=OUT/'OdinUniXNU.c'
text=Path(__file__).with_name('OdinUniXNUHandoff.c').read_text()
remote=ROOT/'work/UniXNU-odin/build/remote-media-u64'
remote=ROOT/('work/UniXNU-odin/build/remote-media-'+options.remote_tag)
if options.remote_media:
 text=text.replace('VOID OdinRunDiagnostic(VOID) {','EFI_STATUS EFIAPI OdinRemoteMediaEntry(EFI_HANDLE,EFI_SYSTEM_TABLE*);\nEFI_STATUS OdinRemoteHandshake(VOID);\nEFI_STATUS OdinRemoteInstallLoaderGuard(VOID);\nVOID OdinRemoteBootStatus(CONST CHAR8*,EFI_STATUS);\nVOID OdinRemoteRecovery(VOID);\nVOID OdinRunDiagnostic(VOID) {')
 text=text.replace(' // This diagnostic must retain',
   ' Status=gBS->SetWatchdogTimer(0,0,0,NULL);\n if(EFI_ERROR(Status)){Record(Status);goto Hold;}\n Record(OdinRemoteMediaEntry(gImageHandle,gST));\n if(EFI_ERROR(mStatus[0]))goto Hold;\n Record(OdinRemoteHandshake());\n if(EFI_ERROR(mStatus[1]))goto Hold;\n // This diagnostic must retain')
 text=text.replace('UniXNU u05 / EFI + initrd','UniXNU u65 / USB desktop')
 text=text.replace(' Status=gBS->StartImage(Image,NULL,NULL);',
   ' Status=OdinRemoteInstallLoaderGuard();\n OdinRemoteBootStatus("loader-guard",Status);\n if(EFI_ERROR(Status))goto Hold;\n Status=gBS->StartImage(Image,NULL,NULL);\n OdinRemoteBootStatus("manager-return",Status);')
 text=text.replace(' for(;;)gBS->Stall(1000000);',' OdinRemoteRecovery();\n for(;;)gBS->Stall(1000000);')
 text=text.replace(' Record(OdinRemoteMediaEntry(gImageHandle,gST));',' Status=OdinRemoteMediaEntry(gImageHandle,gST);Record(Status);')
 text=text.replace(' Record(OdinRemoteHandshake());',' Status=OdinRemoteHandshake();Record(Status);')
 text=text.replace('Hold:\n','Hold:\n OdinRemoteBootStatus("bds-return",Status);\n')
source.write_text(text)
(OUT/'build.log').write_text('')
obj=OUT/'OdinUniXNU.obj'
run([BIN/'clang.exe',*v['CC_FLAGS'].split(),*v['INC'].split(),'-c',source,'-o',obj])
objects=[BM/'OUTPUT/BootManager.obj',BM/'OUTPUT/KeyCallback.obj',obj]
if options.remote_media:
 remoteobj=OUT/'OdinRemoteMedia.obj'
 run([BIN/'clang.exe',*v['CC_FLAGS'].split(),*v['INC'].split(),'-I',remote,
      '-I',ROOT/'work/UniXNU-source/UniXNU-04573c510c5fd4892ca6948739389141cc9e05f5/package/UniXNUPkg/Include',
      '-I',MU/'Silicon/Qualcomm/QcomPkg/Include',
      *(['-DODIN_RESIDENT_CORE7=1'] if options.resident_core7 else []),
      *(['-DODIN_KERNEL_READBACK=1'] if options.kernel_readback else []),
      '-c',remote/'OdinRemoteMedia.c','-o',remoteobj])
 objects.append(remoteobj)
lib=OUT/'BootManagerLib.lib';lib.unlink(missing_ok=True)
run([BIN/'llvm-ar.exe','rcs',lib,*objects])
libs=[Path(p.strip()) for p in (BDS/'OUTPUT/static_library_files.lst').read_text().splitlines()]
libs=[lib if p.name=='BootManagerLib.lib' else p for p in libs]
dll=OUT/'BdsDxe.dll';efi=OUT/'BdsDxe.efi'
run([BIN/'lld-link.exe',*d['DLINK_FLAGS'].split(),'/OUT:'+str(dll),*libs])
run([BT/'GenFw.exe','-e','DXE_DRIVER','-o',efi,dll])
record={'efi_sha256':hashlib.sha256(efi.read_bytes()).hexdigest(),'bytes':efi.stat().st_size,
 'shared_sources_modified':False,'app_guid':'9B665204-A133-47A2-9396-9E2B370A4E25',
 'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [source,*objects,*libs]],
 'device_tested':False,'diagnostic_revision':'u65' if options.remote_media else 'u05','remote_media':options.remote_media,
 'retains_return_status':True,'falls_through_to_bds':False,
 'status_rows':{'0400':'disable diagnostic watchdog','0401':'get FV section',
 '0402':'LoadImage','0403':'loaded image protocol','0404':'before StartImage',
 '0405':'StartImage returned','0406':'UnloadImage'}}
if options.remote_media:
 record['status_rows']={'0400':'install read-only remote filesystem','0401':'USB handshake',
 '0402':'disable diagnostic watchdog','0403':'get FV section','0404':'LoadImage',
 '0405':'loaded image protocol','0406':'before StartImage','0407':'StartImage returned'}
 record['loader_failure_recovery']='Intercept DarwinBoot return before menu; retain EFI status and pump read-only USB with reboot support. No recovery after ExitBootServices.'
(OUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(efi,record['efi_sha256'])
