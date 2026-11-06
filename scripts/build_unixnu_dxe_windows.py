"""Compile the pinned UniXNU DXE drivers against measured Mu libraries."""
from pathlib import Path
import runpy,hashlib,json,subprocess,struct,zlib
data=runpy.run_path(str(Path(__file__).with_name('build_unixnu_windows.py')))
ctx=data['context'];ROOT,MU,UP,BIN,BUILD=[ctx[k] for k in ('ROOT','MU','UP','BIN','BUILD')]
for name in ('UniXNUDxe','UniXNURamDiskDxe'):
 out=ROOT/'work/UniXNU-odin/build'/name;out.mkdir(parents=True,exist_ok=True)
 entry=data['autogen'].replace('UniXNUApplicationEntry',name+'Entry')
 # PcdGetPtr expects an address, not a serialized textual GUID.
 header='#include <PiDxe.h>\n'+data['header']+'\nstatic const EFI_GUID OdinApplicationFile = {0x9b665204,0xa133,0x47a2,{0x93,0x96,0x9e,0x2b,0x37,0x0a,0x4e,0x25}};\n#define _PCD_GET_MODE_PTR_PcdUniXNUApplicationFile ((VOID*)&OdinApplicationFile)\n'
 (out/'OdinEntry.c').write_text(entry);(out/'OdinAutoGen.h').write_text(header)
 inc=[out,*data['includes'][1:]]
 flags=ctx['flags']+['-include',str(out/'OdinAutoGen.h')]+[v for p in inc for v in ('-I',str(p))]
 objects=[];commands=[];log=[]
 source=UP/f'package/UniXNUPkg/Driver/{name}/{name}.c'
 if name=='UniXNURamDiskDxe':
  import sys
  sys.path.insert(0,str(Path(__file__).parent))
  from prepare_odin_ramdisk_source import prepare
  source=prepare(ROOT,source,out)

 for src in (source,out/'OdinEntry.c'):
  obj=out/(src.stem+'.obj');cmd=[BIN/'clang.exe',*flags,'-c',src,'-o',obj]
  p=subprocess.run(cmd,capture_output=True,text=True);log.append(p.stdout+p.stderr);commands.append(list(map(str,cmd)))
  if p.returncode:raise SystemExit(p.stdout+p.stderr)
  objects.append(obj)
 libs=list(ctx['libraries'])
 if name=='UniXNURamDiskDxe':
  libs.append(BUILD/'MdePkg/Library/DxeHobLib/DxeHobLib/OUTPUT/DxeHobLib.lib')
  objects.extend(p for p in data['OUT'].glob('*.obj') if p.name.split('-',1)[1].startswith(('FdtLib.','LibFdtWrapper.','fdt')))
 efi=out/(name+'.efi')
 cmd=[BIN/'lld-link.exe','/nodefaultlib','/entry:OdinEntry','/subsystem:efi_boot_service_driver','/dll','/machine:arm64','/base:0','/align:4096','/timestamp:0','/out:'+str(efi),*objects,*libs]
 p=subprocess.run(cmd,capture_output=True,text=True);log.append(p.stdout+p.stderr);commands.append(list(map(str,cmd)))
 (out/'build.log').write_text(''.join(log));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 if p.returncode:raise SystemExit(p.stdout+p.stderr)
 b=efi.read_bytes();pe=int.from_bytes(b[0x3c:0x40],'little')
 assert b[pe:pe+4]==b'PE\0\0' and int.from_bytes(b[pe+4:pe+6],'little')==0xaa64
 assert int.from_bytes(b[pe+24+68:pe+24+70],'little')==11
 record={'file':efi.name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'arm64_efi_driver':True,'runtime_tested':False}
 (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(record)
