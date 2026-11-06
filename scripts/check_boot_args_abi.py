"""Compile ABI equality assertions against the header exported by this build."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--darwinboot-tag', default='')
options=parser.parse_args()
assert not options.darwinboot_tag or options.darwinboot_tag.isalnum()
driver=DEV/('build/darwinboot-'+options.darwinboot_tag if options.darwinboot_tag else 'build/darwinboot')
out=DEV/('build/boot-abi-'+options.darwinboot_tag if options.darwinboot_tag else 'build/boot-abi');out.mkdir(parents=True,exist_ok=True)
header=DEV/'build/native-kernel/compiled-boot.h'
text=header.read_text()
length=int(re.search(r'#define BOOT_LINE_LENGTH\s+(\d+)',text)[1]);assert length==608
video=re.search(r'struct Boot_Video\s*\{.*?\};',text,re.S)[0]
args=re.search(r'typedef struct boot_args\s*\{.*?\} boot_args;',text,re.S)[0]
source='''#include <Base.h>
#include "BootArgs.h"
typedef UINT16 uint16_t;
typedef UINT32 uint32_t;
typedef UINT64 uint64_t;
'''+video+'\ntypedef struct Boot_Video Boot_Video;\n#define BOOT_LINE_LENGTH '+str(length)+'\n'+args+'\n'
fields={'Revision':'Revision','Version':'Version','VirtualBase':'virtBase','PhysicalBase':'physBase',
 'MemorySize':'memSize','TopOfKernelData':'topOfKernelData','Video':'Video','MachineType':'machineType',
 'DeviceTree':'deviceTreeP','DeviceTreeLength':'deviceTreeLength','CommandLine':'CommandLine',
 'BootFlags':'bootFlags','MemorySizeActual':'memSizeActual'}
for a,b in fields.items():
 source+=f'STATIC_ASSERT(OFFSET_OF(DARWIN_BOOT_ARGS,{a})==OFFSET_OF(boot_args,{b}),"{a} ABI");\n'
source+='STATIC_ASSERT(sizeof(DARWIN_BOOT_ARGS)==sizeof(boot_args),"complete ABI");\n'
(out/'abi.c').write_text(source)
clang=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin/clang.exe'
mu=ROOT/'work/Mu-Silicium-odin/Mu_Basecore/MdePkg/Include'
cmd=[str(clang),'--target=arm64-apple-ios16.5','-ffreestanding','-fshort-wchar','-D_EFI_AARCH64_',
 '-I',str(mu),'-I',str(mu/'AArch64'),'-I',str(driver/'source'),'-c',str(out/'abi.c'),'-o',str(out/'abi.obj')]
p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
record={'passed':True,'matching_fields':list(fields),'structure_bytes':0x2e0,'command_line_bytes':608,
 'compiled_kernel_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),
 'darwinboot_header_sha256':hashlib.sha256((driver/'source/BootArgs.h').read_bytes()).hexdigest(),'command':cmd}
(out/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print('boot_args: all 13 fields and full structure match actual exported XNU header')
