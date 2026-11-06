"""Rebuild the native touch candidate in the existing private build guest."""
from pathlib import Path
import shutil,subprocess,sys
from build_odin_display_owner import SSH,SCP
DEV=Path(__file__).resolve().parents[1];OUT=DEV/'build/touch-metal-u75'
SSH[SSH.index('-i')+1]=str(DEV/'build/touch-metal-u74/guest-ssh-key');SCP[SCP.index('-i')+1]=str(DEV/'build/touch-metal-u74/guest-ssh-key')
remote='/home/odin/unixnu-odin-build/evidence/odin-touch-u75'
for name in ('OdinStTouch.cpp','OriginalHidDeviceABI.h'):
 shutil.copy2(DEV/'drivers/OdinStTouch'/name,OUT/name)
subprocess.run([*SCP,str(OUT/'OdinStTouch.cpp'),str(DEV/'scripts/compile_touch_u75_guest.py'),'odin@127.0.0.1:'+remote+'/'],check=True)
subprocess.run([*SSH,'python3 '+remote+'/compile_touch_u75_guest.py'],check=True)
subprocess.run([*SCP,'odin@127.0.0.1:'+remote+'/OdinStTouch.o',str(OUT)],check=True)
subprocess.run([sys.executable,str(DEV/'scripts/bind_touch_u75.py')],check=True)
