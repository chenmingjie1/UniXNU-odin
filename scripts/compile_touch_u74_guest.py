"""Compile original-iOS16 HID subclass and ST bridge; compilation only."""
from pathlib import Path
import json, subprocess
root=Path('/home/odin/unixnu-odin-build');up=root/'upstream'
out=root/'evidence/odin-touch-u74';out.mkdir(exist_ok=True)
record=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
base=[];args=record['arguments'];i=0
while i<len(args):
 arg=args[i]
 if arg==record['file']:base+=['SOURCE']
 elif arg=='-o':base+=['-o','OBJECT'];i+=1
 elif arg in ('-MF','-MJ'):i+=1
 elif arg=='-Xclang' and args[i+1].startswith('-W'):i+=1
 elif not arg.startswith(('-W','--ld-path=')) and arg not in ('-MD','-MP','-w'):base.append(arg)
 i+=1
base+=['-I',str(out),'-I',str(up/'build/storage-abi/include'),'-I',str(up/'.cache/xnu-work/osfmk'),'-include',str(root/'evidence/odin-storage-abi-u12/odin-ios-target.h'),'-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-deprecated-declarations','-Wno-c99-designator','-Wno-reorder-init-list','-Wno-deprecated-enum-enum-conversion','-Wno-missing-field-initializers','-Wno-c99-extensions','-Wno-missing-braces','-g']
for name in ('OdinStTouch.cpp','OdinStHidBridge.c','OdinTouchController.c'):
 obj=out/(Path(name).stem+'.o');command=['-x','c++']
 command=[base[0],*command,*[str(out/name) if x=='SOURCE' else str(obj) if x=='OBJECT' else x for x in base[1:]]]
 (out/(name+'.command.json')).write_text(json.dumps(command,indent=2)+'\n')
 r=subprocess.run(command,cwd=record['directory'],capture_output=True,text=True)
 (out/(name+'.log')).write_text(r.stdout+r.stderr)
 if r.returncode:raise SystemExit(r.stdout+r.stderr)
print('HID + ST sources compiled with target kernel recipe')
