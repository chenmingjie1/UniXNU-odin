"""Compile the board-gated A660 backend; no phone commands."""
from pathlib import Path
import subprocess
from build_odin_display_owner import SSH,SCP
D=Path(__file__).resolve().parents[1];O=D/'build/gpu-port-u79';remote='/home/odin/unixnu-odin-build/evidence/odin-gpu-u79'
for v in (SSH,SCP):v[v.index('-i')+1]=str(D/'build/touch-metal-u74/guest-ssh-key')
subprocess.run([*SSH,"mkdir -p "+remote],check=True)
files=[*list((D/'drivers/OdinAdreno').glob('*.c')),*list((D/'drivers/OdinAdreno').glob('*.cpp')),*list((D/'drivers/OdinAdreno').glob('*.h')),O/'OdinAdrenoFirmware.c',O/'compile_gpu_guest.py',O/'link_gpu_guest.py']
subprocess.run([*SCP,*map(str,files),'odin@127.0.0.1:'+remote+'/'],check=True)
subprocess.run([*SSH,'python3 '+remote+'/compile_gpu_guest.py'],check=True)
for name in ('OdinAdrenoCore.o','OdinAdrenoFirmware.o','OdinAdrenoService.o','OdinAdrenoOwner.o'):
 subprocess.run([*SCP,'odin@127.0.0.1:'+remote+'/'+name,str(O/name)],check=True)
subprocess.run([*SSH,'llvm-nm --undefined-only '+remote+'/OdinAdrenoCore.o'],check=True)

subprocess.run([*SSH,'python3 '+remote+'/link_gpu_guest.py'],check=True)
subprocess.run([*SCP,'odin@127.0.0.1:'+remote+'/native-real-iig.macho',str(O/'native-real-iig.macho')],check=True)
import sys
subprocess.run([sys.executable,str(D/'scripts/prepare_ios16_prelink.py'),'--kernel',str(O/'native-real-iig.macho'),'--output-dir',str(O),'--driver-policy',str(D/'configs/original-driver-policy.toml')],check=True)
subprocess.run([sys.executable,str(D/'scripts/audit_ios16_prelink.py'),'--input-dir',str(O)],check=True)
