from pathlib import Path
import hashlib,json,struct,subprocess,shutil,sys
r=Path('/home/odin/unixnu-odin-build');o=r/'evidence/odin-gpu-u85';up=r/'upstream'
sys.path.insert(0,str(r));from native_prelink import macho
src=o/'OdinAdrenoService.o';late=o/'OdinAdrenoService.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',str(src),str(late)],check=True)
b=bytearray(late.read_bytes());m=macho(b);at=next(a for c,a,_ in m['commands'] if c==2);sy,n,st,ss=struct.unpack_from('<4I',b,at+8);found=[]
for i in range(n):
 p=sy+i*16;ix,kind,sec,desc,va=struct.unpack_from('<IBBHQ',b,p);name=b[st+ix:b.index(0,st+ix)].decode()
 if name=='__GLOBAL__sub_I_OdinAdrenoService.cpp':found.append(p+4)
assert len(found)==1
b[found[0]]|=1;late.write_bytes(b)
archive=o/'libOdinAdreno.a'
subprocess.run(['llvm-ar','rcs',str(archive),str(late),str(o/'OdinAdrenoOwner.o'),str(o/'OdinAdrenoCore.o'),str(o/'OdinAdrenoFirmware.o'),str(o/'OdinUIThreadSampler.o'),str(o/'OdinUIThreadState.o'),str(o/'OdinUIPolicy.o')],check=True)
p=up/'.cache/xnu-work/bsd/kern/kern_exec.c';before=p.read_text();anchor='\todin_touch_owner_start();';assert before.count(anchor)==1
(o/'kern_exec.before-gpu.c').write_text(before)
try:
 p.write_text(before.replace(anchor,anchor+'\n\textern void odin_gpu_owner_start(void);\n\todin_gpu_owner_start();'))
 (up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o').unlink(missing_ok=True)
 link=(r/'evidence/odin-touch-u75/link_kernel.sh').read_text().replace('evidence/odin-touch-u75/kernel-','evidence/odin-gpu-u85/kernel-')
 assert 'odin-display-owner-u62/libOdinDisplay.a' in link
 link=link.replace('odin-display-owner-u62/libOdinDisplay.a','odin-display-owner-u82/libOdinDisplay.a')
 link=link.replace('archives="','archives="-Wl,-force_load,'+str(archive)+' ',1)
 (o/'link_kernel.sh').write_text(link)
 subprocess.run(['bash',str(o/'link_kernel.sh')],check=True)
 shutil.copy2(up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',o/'native-real-iig.macho')
finally:p.write_text(before)
print('Native source kernel linked: u74 touch + board-gated A660 + GPU user client')
