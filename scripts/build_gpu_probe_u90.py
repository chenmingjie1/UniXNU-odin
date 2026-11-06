"""Isolated u89-derived kernel: fixed probe observations and UI exit reasons.

No new GPU execution path, no device operations, no change to original kext code.
"""
from pathlib import Path
import subprocess
import sys
from build_odin_display_owner import SSH, SCP

D = Path(__file__).resolve().parents[1]
OUT = D / 'build/gpu-probe-u90'
REMOTE = '/home/odin/unixnu-odin-build/evidence/odin-gpu-probe-u90'
for command in (SSH, SCP):
    command[command.index('-i') + 1] = str(D / 'build/touch-metal-u74/guest-ssh-key')


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT / 'kernel.prelinked.experimental.macho').exists()
    guest = OUT / 'compile_link_guest.py'
    guest.write_text('''from pathlib import Path
import json,subprocess,shutil,difflib
r=Path('/home/odin/unixnu-odin-build');up=r/'upstream';o=r/'evidence/odin-gpu-probe-u90';old=r/'evidence/odin-gpu-u85'
record=json.loads((old/'OdinUIPolicy.c.command.json').read_text())
cmd=[str(o/'OdinUIPolicy.c') if v==str(old/'OdinUIPolicy.c') else str(o/'OdinUIPolicy.o') if v==str(old/'OdinUIPolicy.o') else v for v in record]
working=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o.json').read_text().strip().rstrip(','))['directory']
p=subprocess.run(cmd,cwd=working,capture_output=True,text=True);(o/'compile.log').write_text(p.stdout+p.stderr)
if p.returncode:raise SystemExit(p.stdout+p.stderr)
archive=o/'libOdinAdreno.a';shutil.copy2(old/'libOdinAdreno.a',archive)
subprocess.run(['llvm-ar','r',str(archive),str(o/'OdinUIPolicy.o')],check=True)
link=(r/'evidence/odin-touch-edge-u89/link_kernel.sh').read_text()
assert link.count(str(old/'libOdinAdreno.a'))==1
link=link.replace(str(old/'libOdinAdreno.a'),str(archive)).replace('evidence/odin-touch-edge-u89/kernel-','evidence/odin-gpu-probe-u90/kernel-')
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
 (o/'kern_exit.patch').write_text(''.join(difflib.unified_diff(before_exit.splitlines(True),exitfile.read_text().splitlines(True),fromfile='bsd/kern/kern_exit.c',tofile='bsd/kern/kern_exit.c')))
 for name in ('kern_exec','kern_exit'):(up/('build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/'+name+'.o')).unlink(missing_ok=True)
 subprocess.run(['bash',str(o/'link_kernel.sh')],check=True)
 shutil.copy2(up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',o/'native-real-iig.macho')
finally:
 execfile.write_text(before_exec);exitfile.write_text(before_exit)
print('u90 kernel linked; source exit hook only records SpringBoard/backboardd exits')
''')
    subprocess.run([*SSH, 'mkdir -p ' + REMOTE], check=True)
    subprocess.run([*SCP, str(D / 'drivers/OdinAdreno/OdinUIPolicy.c'), str(guest),
                    'odin@127.0.0.1:' + REMOTE + '/'], check=True)
    subprocess.run([*SSH, 'python3 ' + REMOTE + '/compile_link_guest.py'], check=True)
    for name in ('native-real-iig.macho', 'OdinUIPolicy.o', 'compile.log', 'kern_exit.patch'):
        subprocess.run([*SCP, 'odin@127.0.0.1:' + REMOTE + '/' + name, str(OUT / name)], check=True)
    for script in ('prepare_ios16_prelink.py', 'audit_ios16_prelink.py'):
        arguments = ['--kernel', str(OUT / 'native-real-iig.macho'), '--output-dir', str(OUT),
                     '--driver-policy', str(D / 'configs/original-driver-policy.toml')] if script.startswith('prepare') else ['--input-dir', str(OUT)]
        subprocess.run([sys.executable, str(D / 'scripts' / script), *arguments], check=True)


if __name__ == '__main__':
    main()
