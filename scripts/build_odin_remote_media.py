"""Build a read-only USB UEFI filesystem for exact staged u63 desktop inputs."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import argparse
import struct

DEV=Path(__file__).resolve().parents[1]
ROOT=DEV.parents[1]
MU=ROOT/'work/Mu-Silicium-odin'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag',default='u64')
parser.add_argument('--media-tag',default='u63')
parser.add_argument('--resident-core7',action='store_true')
parser.add_argument('--kernel-readback',action='store_true')
options=parser.parse_args()
assert options.tag.isalnum() and options.media_tag.isalnum()
assert not options.kernel_readback or options.resident_core7
OUT=DEV/('build/remote-media-'+options.tag)
OUT.mkdir(exist_ok=True)
ESP=DEV/('build/device-desktop-'+options.media_tag+'/esp/EFI/UniXNU')
paths=[('\\',None),('\\EFI',None),('\\EFI\\UniXNU',None),('\\EFI\\UniXNU\\Payloads',None)]
paths += [('\\EFI\\UniXNU\\'+str(p.relative_to(ESP)).replace('/','\\'),p)
          for p in sorted(ESP.rglob('*')) if p.is_file()]
records=[]
header='STATIC CONST REMOTE_FILE mFiles[]={\n'
for index,(name,path) in enumerate(paths):
    size=path.stat().st_size if path else 0
    header+=' {L"'+name.replace('\\','\\\\')+'",'+str(size)+'ULL},\n'
    records.append({'id':index,'uefi_path':name,'path':str(path) if path else None,'bytes':size})
header+='};\n'
(OUT/'OdinRemoteFiles.h').write_text(header)
vendor=MU/'Silicon/Qualcomm/QcomPkg/Include/Protocol/EFIUsbDevice.h'
vendor_text=vendor.read_text()
assert vendor_text.count('#include <Protocol/EFIUsbEx.h>')==1
# This older vendor header collides with current MdePkg USB BOS declarations.
# Keep the protocol ABI unchanged and supply only its missing qualifier type.
vendor_text=vendor_text.replace('#include <Protocol/EFIUsbEx.h>', '''
#pragma pack(push,1)
typedef struct { UINT8 Length, DescriptorType; UINT16 BcdUSB;
  UINT8 DeviceClass, DeviceSubClass, DeviceProtocol, MaxPacketSize0,
        NumConfigurations, Reserved; } EFI_USB_DEVICE_QUALIFIER_DESCRIPTOR;
typedef EFI_USB_DEVICE_QUALIFIER_DESCRIPTOR USB_DEVICE_QUALIFIER_DESCRIPTOR;
#pragma pack(pop)
''')
(OUT/'Protocol').mkdir(exist_ok=True)
(OUT/'Protocol/EFIUsbDevice.h').write_text(vendor_text)
source=DEV/'firmware/OdinRemoteMedia.c'
shutil.copy2(source,OUT/source.name)
shutil.copy2(DEV/'firmware/OdinRemoteProtocol.h',OUT/'OdinRemoteProtocol.h')
shutil.copy2(DEV/'firmware/OdinResident.h',OUT/'OdinResident.h')
if options.kernel_readback:
 shutil.copy2(DEV/'firmware/OdinKernelReadback.h',OUT/'OdinKernelReadback.h')
 kernel=(ESP/'Payloads/kernel.macho').read_bytes();pos=32;symbols={};base_va=2**64-1
 for _ in range(struct.unpack_from('<I',kernel,16)[0]):
  kind,size=struct.unpack_from('<II',kernel,pos)
  if kind==2:symoff,count,stroff,strbytes=struct.unpack_from('<4I',kernel,pos+8)
  if kind==25:
   va,vs=struct.unpack_from('<2Q',kernel,pos+24)
   if vs:base_va=min(base_va,va)
  pos+=size
 for i in range(count):
  name,kind,sect,desc,value=struct.unpack_from('<IBBHQ',kernel,symoff+i*16)
  if kind&0xe==0xe:
   start=stroff+name;end=kernel.index(b'\0',start,stroff+strbytes)
   symbols[kernel[start:end].decode('utf-8','replace')]=value
 required={'STAGE':'_odin_platform_last_stage',
           'LOG_BASE':'_debug_buf_base','LOG_PTR':'_debug_buf_ptr','LOG_SIZE':'_debug_buf_size'}
 header=f'#define ODIN_KERNEL_BASE 0x{base_va:x}ULL\n'
 for label,name in required.items():
  assert name in symbols,name
  assert 0<=symbols[name]-base_va<0x100000000
  header+=f'#define ODIN_{label}_OFFSET 0x{symbols[name]-base_va:x}ULL\n'
 for label,name in {'POSTVM':'_odin_postvm_last_stage','POSTCALLER':'_odin_postvm_last_caller',
                    'PANIC_STR':'_debugger_panic_str','PANIC_CALLER':'_debugger_panic_caller',
                    'PANIC_ARGS':'_debugger_panic_args','TOUCH_STATS':'_odin_touch_stats',
                    'HID_STATS':'_odin_hid_stats','GPU_STATS':'_odin_gpu_stats','PRESENT_STATS':'_odin_present_stats',
                    'SURFACE_STATS':'_odin_surface_inspections',
                    'UI_THREADS':'_odin_ui_threads',
                    'UI_POLICY':'_odin_ui_policy','UI_POLICY_COMMAND':'_odin_ui_policy_command',
                    'GPU_LOG':'_odin_gpu_log','GPU_LOG_USED':'_odin_gpu_log_used'}.items():
  if name in symbols:
   assert 0<=symbols[name]-base_va<0x100000000
   header+=f'#define ODIN_{label}_OFFSET 0x{symbols[name]-base_va:x}ULL\n'
 (OUT/'OdinKernelSymbols.h').write_text(header)
entry=(DEV/'build/darwinboot-u63/OdinEntry.c').read_text().replace('DarwinBootEntry','OdinRemoteMediaEntry')
(OUT/'OdinEntry.c').write_text(entry)
command=json.loads((DEV/'build/darwinboot-u63/commands.json').read_text())
compile_base=command[0]
base=compile_base[:compile_base.index('-c')]
base+=['-I',str(OUT),'-I',str(MU/'Silicon/Qualcomm/QcomPkg/Include')]
if options.resident_core7:base+=['-DODIN_RESIDENT_CORE7=1']
if options.kernel_readback:base+=['-DODIN_KERNEL_READBACK=1']
commands=[]
logs=[]
def run(cmd):
    commands.append(cmd)
    r=subprocess.run(cmd,capture_output=True,text=True)
    logs.append(r.stdout+r.stderr)
    (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    (OUT/'build.log').write_text(''.join(logs))
    if r.returncode:raise SystemExit(r.stdout+r.stderr)
objects=[]
for name in ('OdinRemoteMedia','OdinEntry'):
    obj=OUT/(name+'.obj')
    run([*base,'-c',str(OUT/(name+'.c')),'-o',str(obj)])
    objects.append(str(obj))
link=command[-1]
libs=[x for x in link if x.endswith('.lib')]
efi=OUT/'OdinRemoteMedia.efi'
run([link[0],'/nodefaultlib','/entry:OdinEntry','/subsystem:efi_boot_service_driver',
     '/dll','/machine:arm64','/base:0','/align:4096','/timestamp:0','/out:'+str(efi),*objects,*libs])
raw=efi.read_bytes();pe=int.from_bytes(raw[0x3c:0x40],'little')
assert raw[pe:pe+4]==b'PE\0\0' and int.from_bytes(raw[pe+4:pe+6],'little')==0xaa64
report={'artifact':str(efi),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
        'files':records,'arm64_uefi_driver':True,'device_tested':False,'read_only':True,
        'read_only_scope':'device filesystem and partitions',
        'fixed_ram_ui_policy_control':bool(options.kernel_readback),
        'full_media_preallocation':False,'maximum_response_bytes':0x100020,
        'wire_header':'<8sIIQII: ODNRD001, sequence, file ID, offset, size, CRC32',
        'vendor_usb_header':str(MU/'Silicon/Qualcomm/QcomPkg/Include/Protocol/EFIUsbDevice.h'),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'resident_core7':options.resident_core7,'media_tag':options.media_tag,'kernel_readback':options.kernel_readback}
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('Built',efi.name,len(raw),'bytes; read-only files:',len(records)-4)
