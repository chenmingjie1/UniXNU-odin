#!/usr/bin/env python3
"""Build the LLVM 14 kernel profile runtime with XNU 8796-compatible ABI."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path('/home/odin/unixnu-odin-build')
UP=ROOT/'upstream'
SDK=Path('/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk')
SRC=ROOT/'profile-runtime/compiler-rt'
OUT=UP/'build/cc-kext-llvm14'
OUT.mkdir(parents=True,exist_ok=True)
names=['InstrProfiling','InstrProfilingBuffer','InstrProfilingPlatformDarwin','InstrProfilingWriter','InstrProfilingInternal','InstrProfilingVersionVar']
commands=[]
for name in names:
    command=['/usr/bin/clang','-target','arm64-apple-ios16.5','-isysroot',str(SDK),'-mkernel','-ffreestanding','-DKERNEL_USE',
             '-O3','-fPIC','-w','-I',str(SRC/'include'),'-I',str(SDK/'System/Library/Frameworks/Kernel.framework/Headers'),
             '-I','/home/odin/xnu-work/project/xnu-deps/MacOSX13.3.sdk/usr/include',
             '-c',str(SRC/'lib/profile'/(name+'.c')),'-o',str(OUT/(name+'.o'))]
    commands.append(command)
    result=subprocess.run(command,capture_output=True,text=True)
    (OUT/(name+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:raise SystemExit(result.stdout+result.stderr)
    print(name,'compiled',flush=True)
archive=OUT/'libcc_kext.a'
subprocess.run(['/usr/bin/llvm-ar','--format=darwin','rcs',str(archive),*[str(OUT/(n+'.o')) for n in names]],check=True)
(OUT/'verification.json').write_text(json.dumps({'revision':'f28c006a5895fc0e329fe15fead81e37457cb1d1','llvm_version':'14.0.6','sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'commands':commands},indent=2)+'\n')
