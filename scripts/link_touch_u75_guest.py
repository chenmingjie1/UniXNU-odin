"""Late HID metaclass registration and source-owned launch hook; retain u73."""
from pathlib import Path
import hashlib,json,struct,subprocess,shutil,sys
root=Path('/home/odin/unixnu-odin-build');out=root/'evidence/odin-touch-u75';up=root/'upstream'
sys.path.insert(0,str(root));from native_prelink import macho
cmd=json.loads((out/'OdinStTouch.cpp.command.json').read_text());compiler=cmd[0]
subprocess.run([compiler,'-target','arm64-apple-ios16.0','-c',str(out/'hid-original-bindings.S'),'-o',str(out/'hid-original-bindings.o')],check=True)
obj=out/'OdinStTouch.o';late=out/'OdinStTouch.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',obj,late],check=True)
b=bytearray(late.read_bytes());m=macho(b);at=next(a for c,a,_ in m['commands'] if c==2)
sy,count,strings,ss=struct.unpack_from('<4I',b,at+8);found=[]
for i in range(count):
 p=sy+i*16;ix,kind,sec,desc,va=struct.unpack_from('<IBBHQ',b,p)
 name=b[strings+ix:b.index(0,strings+ix)].decode()
 if name=='__GLOBAL__sub_I_OdinStTouch.cpp':found.append(p+4)
assert len(found)==1
b[found[0]]|=1
assert not any(s['name']=='__mod_init_func' for g in m['segments'] for s in g['sections'])
late.write_bytes(b)
archive=out/'libOdinStTouch.a'
subprocess.run(['llvm-ar','rcs',str(archive),str(late),str(out/'OdinStHidBridge.o'),str(out/'OdinTouchController.o'),str(out/'hid-original-bindings.o')],check=True)
p=up/'.cache/xnu-work/bsd/kern/kern_exec.c';before=p.read_text()
needle='\todin_display_owner_start();'
if 'odin_touch_owner_start();' not in before:
 assert before.count(needle)==1
 (out/'kern_exec.before-touch.c').write_text(before)
 p.write_text(before.replace(needle,needle+'\n\textern void odin_touch_owner_start(void);\n\todin_touch_owner_start();'))
obj=up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o'
obj.unlink(missing_ok=True)
link=(root/'evidence/odin-pmgr-u73/link_kernel.sh').read_text().replace('evidence/odin-pmgr-u73/kernel-','evidence/odin-touch-u75/kernel-')
link=link.replace('archives="','archives="-Wl,-force_load,'+str(archive)+' ',1)
(out/'link_kernel.sh').write_text(link)
subprocess.run(['bash',str(out/'link_kernel.sh')],check=True)
shutil.copy2(up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',out/'native-real-iig.macho')
print('Source XNU linked: u73 desktop + exact iOS16 HID device + ST worker')
