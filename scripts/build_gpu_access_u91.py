"""Rebuild GPU service access on u90, authorized for temporary RAM boot only.

Computer build only. Retain the signed u90 probe and original Apple driver code.
"""
from pathlib import Path
import subprocess
import sys
from build_odin_display_owner import SSH, SCP

D = Path(__file__).resolve().parents[1]
OUT = D / 'build/gpu-access-u91'
REMOTE = '/home/odin/unixnu-odin-build/evidence/odin-gpu-access-u91'
for command in (SSH, SCP):
    command[command.index('-i') + 1] = str(D / 'build/touch-metal-u74/guest-ssh-key')


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT / 'kernel.prelinked.experimental.macho').exists()
    guest = OUT / 'compile_link_guest.py'
    guest.write_text('''from pathlib import Path
import json,subprocess,shutil,struct,sys
r=Path('/home/odin/unixnu-odin-build');up=r/'upstream';o=r/'evidence/odin-gpu-access-u91';old=r/'evidence/odin-gpu-probe-u90'
sys.path.insert(0,str(r));from native_prelink import macho
record=json.loads((r/'evidence/odin-touch-u74/OdinStTouch.cpp.command.json').read_text())
cmd=[str(o/'OdinAdrenoService.cpp') if v.endswith('/OdinStTouch.cpp') else str(o/'OdinAdrenoService.o') if v.endswith('/OdinStTouch.o') else v for v in record]
cmd+=['-I',str(o)]
working=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o.json').read_text().strip().rstrip(','))['directory']
(o/'compile.command.json').write_text(json.dumps(cmd,indent=2))
p=subprocess.run(cmd,cwd=working,capture_output=True,text=True);(o/'compile.log').write_text(p.stdout+p.stderr)
if p.returncode:raise SystemExit(p.stdout+p.stderr)
src=o/'OdinAdrenoService.o';late=o/'OdinAdrenoService.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',str(src),str(late)],check=True)
b=bytearray(late.read_bytes());m=macho(b);at=next(a for c,a,_ in m['commands'] if c==2);sy,n,st,ss=struct.unpack_from('<4I',b,at+8);found=[]
for i in range(n):
 p=sy+i*16;ix,kind,sec,desc,va=struct.unpack_from('<IBBHQ',b,p);name=b[st+ix:b.index(0,st+ix)].decode()
 if name=='__GLOBAL__sub_I_OdinAdrenoService.cpp':found.append(p+4)
assert len(found)==1
b[found[0]]|=1;late.write_bytes(b)
archive=o/'libOdinAdreno.a';shutil.copy2(old/'libOdinAdreno.a',archive)
subprocess.run(['llvm-ar','r',str(archive),str(late)],check=True)
link=(old/'link_kernel.sh').read_text().replace(str(old/'libOdinAdreno.a'),str(archive)).replace('evidence/odin-gpu-probe-u90/kernel-','evidence/odin-gpu-access-u91/kernel-')
(o/'link_kernel.sh').write_text(link)
execfile=up/'.cache/xnu-work/bsd/kern/kern_exec.c';exitfile=up/'.cache/xnu-work/bsd/kern/kern_exit.c'
before_exec=execfile.read_text();before_exit=exitfile.read_text()
anchor='\\todin_touch_owner_start();';assert before_exec.count(anchor)==1
anchor_exit='\\tboot_progress_exit(proc_getpid(p),p->p_name,rv,\\n\\t    p->p_exit_reason ? p->p_exit_reason->osr_namespace : 0,\\n\\t    p->p_exit_reason ? p->p_exit_reason->osr_code : 0);'
assert before_exit.count(anchor_exit)==1
extra='\\n\\textern void odin_ui_exit_note(int,const char *,int,unsigned,uint64_t);\\n\\todin_ui_exit_note(proc_getpid(p),p->p_name,rv,\\n\\t    p->p_exit_reason ? p->p_exit_reason->osr_namespace : 0,\\n\\t    p->p_exit_reason ? p->p_exit_reason->osr_code : 0);'
try:
 if 'odin_gpu_owner_start();' not in before_exec:execfile.write_text(before_exec.replace(anchor,anchor+'\\n\\textern void odin_gpu_owner_start(void);\\n\\todin_gpu_owner_start();'))
 exitfile.write_text(before_exit.replace(anchor_exit,anchor_exit+extra))
 for name in ('kern_exec','kern_exit'):(up/('build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/'+name+'.o')).unlink(missing_ok=True)
 subprocess.run(['bash',str(o/'link_kernel.sh')],check=True)
 shutil.copy2(up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',o/'native-real-iig.macho')
finally:
 execfile.write_text(before_exec);exitfile.write_text(before_exit)
print('u91 kernel linked; service grant restricted to SpringBoard/backboardd')
''')
    subprocess.run([*SSH, 'mkdir -p ' + REMOTE], check=True)
    subprocess.run([*SCP, str(D / 'drivers/OdinAdreno/OdinAdrenoService.cpp'),
                    str(D / 'drivers/OdinAdreno/OdinAdrenoApi.h'), str(guest),
                    'odin@127.0.0.1:' + REMOTE + '/'], check=True)
    subprocess.run([*SSH, 'python3 ' + REMOTE + '/compile_link_guest.py'], check=True)
    for name in ('native-real-iig.macho', 'compile.log', 'compile.command.json'):
        subprocess.run([*SCP, 'odin@127.0.0.1:' + REMOTE + '/' + name, str(OUT / name)], check=True)
    subprocess.run([sys.executable, str(D / 'scripts/prepare_ios16_prelink.py'),
                    '--kernel', str(OUT / 'native-real-iig.macho'), '--output-dir', str(OUT),
                    '--driver-policy', str(D / 'configs/original-driver-policy.toml')], check=True)
    subprocess.run([sys.executable, str(D / 'scripts/audit_ios16_prelink.py'),
                    '--input-dir', str(OUT)], check=True)


if __name__ == '__main__':
    main()
