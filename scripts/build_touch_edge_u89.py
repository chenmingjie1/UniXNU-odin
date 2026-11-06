"""Compile the qualified iOS16 edge hook into an isolated native candidate.

Requires the existing private build guest and u85 build inputs. No device I/O.
"""
from pathlib import Path
import subprocess
import sys
import shutil
from build_odin_display_owner import SSH, SCP

D = Path(__file__).resolve().parents[1]
OUT = D / 'build/touch-edge-u89'
REMOTE = '/home/odin/unixnu-odin-build/evidence/odin-touch-edge-u89'
for command in (SSH, SCP):
    command[command.index('-i') + 1] = str(D / 'build/touch-metal-u74/guest-ssh-key')


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT / 'kernel.prelinked.experimental.macho').exists(), 'Preserve built candidate'
    subprocess.run([sys.executable, str(D / 'scripts/qualify_hid_edge_ios16.py')], check=True)
    files = [D / 'drivers/OdinStTouch' / n for n in
             ('OdinStTouch.cpp', 'OdinTouchEdge16.h', 'OriginalHidDeviceABI.h')]
    files += list((D / 'package/OdinStTouch').glob('*.h'))
    for file in files:
        shutil.copy2(file, OUT / file.name)
    original = (D / 'build/touch-metal-u75/hid-original-bindings.S').read_text()
    bindings = OUT / 'hid-original-bindings.S'
    bindings.write_text(original + (D / 'build/hid-edge-ios16/bindings.S').read_text())
    guest = OUT / 'compile_link_guest.py'
    guest.write_text('''from pathlib import Path
import json,subprocess,struct,sys,shutil
r=Path('/home/odin/unixnu-odin-build');up=r/'upstream';o=r/'evidence/odin-touch-edge-u89'
old=r/'evidence/odin-touch-u75'
recipe=json.loads((old/'OdinStTouch.cpp.command.json').read_text())
cmd=[str(o/'OdinStTouch.cpp') if v.endswith('/OdinStTouch.cpp') else str(o/'OdinStTouch.o') if v.endswith('/OdinStTouch.o') else v for v in recipe]
cmd+=['-I',str(o)]
(o/'compile-command.json').write_text(json.dumps(cmd,indent=2))
record=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
p=subprocess.run(cmd,cwd=record['directory'],capture_output=True,text=True);(o/'compile.log').write_text(p.stdout+p.stderr)
if p.returncode:raise SystemExit(p.stdout+p.stderr)
subprocess.run([cmd[0],'-target','arm64-apple-ios16.0','-c',str(o/'hid-original-bindings.S'),'-o',str(o/'hid-original-bindings.o')],check=True)
sys.path.insert(0,str(r));from native_prelink import macho
src=o/'OdinStTouch.o';late=o/'OdinStTouch.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',str(src),str(late)],check=True)
b=bytearray(late.read_bytes());m=macho(b);at=next(a for c,a,_ in m['commands'] if c==2);sy,n,st,ss=struct.unpack_from('<4I',b,at+8);found=[]
for i in range(n):
 p=sy+i*16;ix,kind,sec,desc,va=struct.unpack_from('<IBBHQ',b,p);name=b[st+ix:b.index(0,st+ix)].decode()
 if name=='__GLOBAL__sub_I_OdinStTouch.cpp':found.append(p+4)
assert len(found)==1;b[found[0]]|=1;late.write_bytes(b)
archive=o/'libOdinStTouch.a'
subprocess.run(['llvm-ar','rcs',str(archive),str(late),str(old/'OdinStHidBridge.o'),str(old/'OdinTouchController.o'),str(o/'hid-original-bindings.o')],check=True)
link=(r/'evidence/odin-gpu-u85/link_kernel.sh').read_text()
needle=str(old/'libOdinStTouch.a');assert link.count(needle)==1
link=link.replace(needle,str(archive)).replace('evidence/odin-gpu-u85/kernel-','evidence/odin-touch-edge-u89/kernel-')
(o/'link_kernel.sh').write_text(link)
p=up/'.cache/xnu-work/bsd/kern/kern_exec.c';before=p.read_text();anchor='\\todin_touch_owner_start();';assert before.count(anchor)==1
try:
 if 'odin_gpu_owner_start();' not in before:p.write_text(before.replace(anchor,anchor+'\\n\\textern void odin_gpu_owner_start(void);\\n\\todin_gpu_owner_start();'))
 (up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o').unlink(missing_ok=True)
 subprocess.run(['bash',str(o/'link_kernel.sh')],check=True)
 shutil.copy2(up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',o/'native-real-iig.macho')
finally:p.write_text(before)
print('u89 native kernel linked; exact-family edge metadata enabled by boot argument only')
''')
    subprocess.run([*SSH, 'mkdir -p ' + REMOTE], check=True)
    subprocess.run([*SCP, *map(str, [*(OUT / f.name for f in files), bindings, guest]),
                    'odin@127.0.0.1:' + REMOTE + '/'], check=True)
    subprocess.run([*SSH, 'python3 ' + REMOTE + '/compile_link_guest.py'], check=True)
    for name in ('native-real-iig.macho', 'OdinStTouch.o', 'compile.log', 'compile-command.json'):
        subprocess.run([*SCP, 'odin@127.0.0.1:' + REMOTE + '/' + name, str(OUT / name)], check=True)
    for script in ('prepare_ios16_prelink.py', 'audit_ios16_prelink.py'):
        args = ['--kernel', str(OUT / 'native-real-iig.macho'), '--output-dir', str(OUT),
                '--driver-policy', str(D / 'configs/original-driver-policy.toml')] if script.startswith('prepare') else ['--input-dir', str(OUT)]
        subprocess.run([sys.executable, str(D / 'scripts' / script), *args], check=True)


if __name__ == '__main__':
    main()
