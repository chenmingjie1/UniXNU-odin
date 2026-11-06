from pathlib import Path
import json,subprocess
r=Path('/home/odin/unixnu-odin-build');up=r/'upstream';o=r/'evidence/odin-gpu-u85'
x=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o.json').read_text().strip().rstrip(','));a=x['arguments'];base=[];i=0
while i<len(a):
 v=a[i]
 if v==x['file']:base+=['SOURCE']
 elif v=='-o':base+=['-o','OBJECT'];i+=1
 elif v in ('-MF','-MJ'):i+=1
 elif v not in ('-MD','-MP') and not v.startswith(('-W','--ld-path=')):base.append(v)
 i+=1
base+=['-I',str(o),'-I',str(up/'build/storage-abi/include'),'-I',str(up/'.cache/xnu-work/osfmk'),'-include',str(r/'evidence/odin-storage-abi-u12/odin-ios-target.h'),'-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-missing-field-initializers','-Wno-deprecated-declarations']
for name in ('OdinAdrenoCore.c','OdinAdrenoFirmware.c','OdinUIThreadSampler.c','OdinUIThreadState.c','OdinUIPolicy.c'):
 cmd=[str(o/name) if v=='SOURCE' else str(o/(Path(name).stem+'.o')) if v=='OBJECT' else v for v in base]
 compile_directory=x['directory']
 if name=='OdinUIThreadState.c':
  tx=json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/thread.o.json').read_text().strip().rstrip(','));args=tx['arguments'];cmd=[];i=0
  while i<len(args):
   v=args[i]
   if v==tx['file']:cmd.append(str(o/name))
   elif v=='-o':cmd+=['-o',str(o/'OdinUIThreadState.o')];i+=1
   elif v in ('-MF','-MJ'):i+=1
   elif v not in ('-MD','-MP') and not v.startswith(('-W','--ld-path=')):cmd.append(v)
   i+=1

  compile_directory=tx['directory']
 (o/(name+'.command.json')).write_text(json.dumps(cmd,indent=2));p=subprocess.run(cmd,cwd=compile_directory,capture_output=True,text=True);(o/(name+'.log')).write_text(p.stdout+p.stderr)
 if p.returncode:raise SystemExit(p.stdout+p.stderr)
print('Native A660 core + private firmware objects compiled')

recipe=json.loads((r/'evidence/odin-touch-u74/OdinStTouch.cpp.command.json').read_text())
for name in ('OdinAdrenoService.cpp','OdinAdrenoOwner.cpp'):
 cmd=[str(o/name) if v.endswith('/OdinStTouch.cpp') else str(o/(Path(name).stem+'.o')) if v.endswith('/OdinStTouch.o') else v for v in recipe]
 cmd+=['-I',str(o)]
 p=subprocess.run(cmd,cwd=x['directory'],capture_output=True,text=True);(o/(name+'.log')).write_text(p.stdout+p.stderr)
 if p.returncode:raise SystemExit(p.stdout+p.stderr)
print('Native GPU service and owner compiled')
