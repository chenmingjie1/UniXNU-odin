"""Rebuild the native touch candidate in the existing private build guest."""
from pathlib import Path
import shutil,subprocess,sys
from build_odin_display_owner import SSH,SCP
DEV=Path(__file__).resolve().parents[1];OUT=DEV/'build/touch-metal-u74'
SSH[SSH.index('-i')+1]=str(OUT/'guest-ssh-key');SCP[SCP.index('-i')+1]=str(OUT/'guest-ssh-key')
remote='/home/odin/unixnu-odin-build/evidence/odin-touch-u74'
for name in ('OdinStTouch.cpp','OriginalHidDeviceABI.h'):
 shutil.copy2(DEV/'drivers/OdinStTouch'/name,OUT/name)
subprocess.run([*SCP,str(OUT/'OdinStTouch.cpp'),str(DEV/'scripts/compile_touch_u74_guest.py'),'odin@127.0.0.1:'+remote+'/'],check=True)
subprocess.run([*SSH,'python3 '+remote+'/compile_touch_u74_guest.py'],check=True)
subprocess.run([*SCP,'odin@127.0.0.1:'+remote+'/OdinStTouch.o',str(OUT)],check=True)
subprocess.run([sys.executable,str(DEV/'scripts/bind_touch_u74.py')],check=True)
