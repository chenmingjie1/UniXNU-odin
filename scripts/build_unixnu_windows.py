"""Build the real pinned UniXNU boot manager with measured Mu dependencies."""
from pathlib import Path
import hashlib,json,re,runpy,subprocess
context=runpy.run_path(str(Path(__file__).with_name('build_darwinboot_windows.py')))
ROOT,MU,UP,BIN,OLD=[context[k] for k in ('ROOT','MU','UP','BIN','OLD')]
OUT=ROOT/'work/UniXNU-odin/build/unixnu-efi'
OUT.mkdir(parents=True,exist_ok=True)
commands=[]
def run(cmd):
    commands.append(list(map(str,cmd)))
    p=subprocess.run(cmd,capture_output=True,text=True)
    with (OUT/'build.log').open('a',encoding='utf-8') as f:f.write(p.stdout+p.stderr)
    (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    if p.returncode:raise SystemExit(p.stdout+p.stderr)

autogen=context['autogen'].replace('DarwinBootEntry','UniXNUApplicationEntry')
guid_values={}
for dec in [MU/'Mu_Basecore/MdePkg/MdePkg.dec',UP/'package/UniXNUPkg/UniXNUPkg.dec']:
    for m in re.finditer(r'^\s*(g\w+)\s*=\s*(\{[^\n]+\})',dec.read_text(),re.M):guid_values[m[1]]=m[2]
for name,value in guid_values.items():
    if not re.search(r'\b'+name+r'\s*=',autogen):autogen+='\nGLOBAL_REMOVE_IF_UNREFERENCED EFI_GUID '+name+' = '+value+';\n'
(OUT/'OdinEntry.c').write_text(autogen)
header='''#include <Uefi.h>
#define _PCD_GET_MODE_32_PcdUniXNUDebugLevel 0x40U
#define _PCD_GET_MODE_PTR_PcdUniXNUConfigPath ((VOID*)L"\\\\EFI\\\\UniXNU\\\\unixnu.toml")
'''
header+='\n'.join('extern EFI_GUID '+name+';' for name in guid_values)+'\n'
(OUT/'OdinAutoGen.h').write_text(header)
fdt=MU/'Mu_Basecore/MdePkg/Library/BaseFdtLib'
includes=[OUT,MU/'Mu_Basecore/MdePkg/Include',MU/'Mu_Basecore/MdePkg/Include/AArch64',UP/'package/UniXNUPkg/Include',fdt,fdt/'libfdt/libfdt']
flags=context['flags']+['-include',str(OUT/'OdinAutoGen.h')]
incflags=[v for p in includes for v in ('-I',str(p))]
sources=[UP/'package/UniXNUPkg/Application/UniXNU/UniXNU.c',*sorted((UP/'package/UniXNUPkg/Library/UniXNULib').glob('*.c')),
         fdt/'FdtLib.c',fdt/'LibFdtWrapper.c',*sorted((fdt/'libfdt/libfdt').glob('fdt*.c')),OUT/'OdinEntry.c']
objects=[]
(OUT/'build.log').write_text('')
for n,source in enumerate(sources):
    obj=OUT/(str(n)+'-'+source.stem+'.obj')
    run([BIN/'clang.exe',*flags,*incflags,'-c',source,'-o',obj])
    objects.append(obj)
efi=OUT/'UniXNU.efi'
run([BIN/'lld-link.exe','/nodefaultlib','/entry:OdinEntry','/subsystem:efi_application','/machine:arm64',
     '/base:0','/align:4096','/timestamp:0','/out:'+str(efi),'/map:'+str(OUT/'UniXNU.map'),*objects,*context['libraries']])
data=efi.read_bytes();pe=int.from_bytes(data[0x3c:0x40],'little')
assert data[pe:pe+4]==b'PE\0\0' and int.from_bytes(data[pe+4:pe+6],'little')==0xaa64
assert int.from_bytes(data[pe+24+68:pe+24+70],'little')==10
(OUT/'verification.json').write_text(json.dumps({'revision':'04573c510c5fd4892ca6948739389141cc9e05f5',
    'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'arm64_efi_application':True,'device_tested':False},indent=2)+'\n')
print('UniXNU.efi',len(data),hashlib.sha256(data).hexdigest())
