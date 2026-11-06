"""Build an opt-in, late-registered display archive in the existing Linux VM.

Computer-only. Does not operate a phone or modify the known-good u12 kernel.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
     '-o','UserKnownHostsFile='+str(ROOT/'outputs/MIX4-odin-porting/kernel-touch-init-integrated-20261101/guest-known-hosts'),
     '-i',str(ROOT/'work/odin-portable-linux/guest-ssh-key'),'-p','18474','odin@127.0.0.1']
# Construct SCP explicitly: SSH's port flag has different case.
SCP=['scp','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
     '-o',SSH[8],'-i',SSH[10],'-P','18474']

def run(args,**kwargs):
    return subprocess.run(args,check=True,cwd=ROOT,**kwargs)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tag',default='u16')
    a=p.parse_args();assert a.tag.isalnum()
    OUT=DEV/('build/display-owner-'+a.tag)
    REMOTE='/home/odin/unixnu-odin-build/evidence/odin-display-owner-'+a.tag
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'kernel.prelinked.experimental.macho').exists(), 'Preserve existing linked candidate; select a new tag'
    run([*SSH,'mkdir -p '+REMOTE])
    source=DEV/'drivers/OdinDisplay'
    files=[source/n for n in ('OriginalLegacyFramebufferABI.h','OdinDisplayABIAnnotation.cpp',
        'OdinLegacyGOPDisplay.cpp','OdinDisplayOwner.cpp','OdinKeyStoreEvents.cpp','OriginalSurface16.h','interface-contract.json')]
    snapshot=OUT/'source';snapshot.mkdir(exist_ok=True)
    for path in files:
        target=snapshot/path.name
        assert not target.exists() or target.read_bytes()==path.read_bytes(), 'Preserve previous source snapshot'
        shutil.copy2(path,target)
    bindings=(DEV/'build/display-analysis-ios16/original-bindings.S').read_text()
    # Qualified against original slot188 and actual client selector28.
    bindings=bindings.replace('__ZN25IOMobileFramebufferLegacy15unclassified188Ev',
                              '__ZN25IOMobileFramebufferLegacy11getDotPitchEPj')
    bindings=bindings.replace('__ZN25IOMobileFramebufferLegacy15unclassified336Ev',
                              '__ZN25IOMobileFramebufferLegacy17applyStateRequestEPK26OriginalLegacyStateRequestb')
    bindings=bindings.replace('__ZN25IOMobileFramebufferLegacy15unclassified282Ev',
                              '__ZN25IOMobileFramebufferLegacy12validateSwapEPKv')
    bindings=bindings.replace('__ZN25IOMobileFramebufferLegacy15unclassified276Ev',
                              '__ZN25IOMobileFramebufferLegacy13kickSwapQueueEv')
    bindings=bindings.replace('__ZN25IOMobileFramebufferLegacy15unclassified281Ev',
                              '__ZN25IOMobileFramebufferLegacy19completeCurrentSwapEv')
    queue_contract=DEV/'build/display-analysis-ios16/u30-queue-contract.json'
    if queue_contract.exists():
        queue=json.loads(queue_contract.read_text())
        assert queue['passed'] and queue['target']=='iOS16.5/20F66'
        bindings+='.globl _odin_original_request_state\n.set _odin_original_request_state, '+queue['request_state_helper']+'\n'
    surface=json.loads((DEV/'build/display-analysis-ios16/u25-surface-contract.json').read_text())
    assert surface['passed'] and surface['target']=='iOS16.5/20F66'
    for name,entry in surface['getters'].items():
        symbol='_odin_surface_'+name
        bindings+=f'.globl {symbol}\n.set {symbol}, {entry["address"]}\n'
    (OUT/'original-bindings.S').write_text(bindings)
    files.append(OUT/'original-bindings.S')
    run([*SCP,*map(str,files),'odin@127.0.0.1:'+REMOTE+'/'])
    compiler=(DEV/'scripts/compile_odin_display_annotation.py').read_text()
    compiler=compiler.replace("evidence/odin-display-abi-u14","evidence/odin-display-owner-"+a.tag)
    (OUT/'compile_display.py').write_text(compiler)
    vm_script='''from pathlib import Path
import hashlib,json,subprocess,struct,sys
sys.path.insert(0,'/home/odin/unixnu-odin-build')
from native_prelink import macho
out=Path('''+repr(REMOTE)+''')
subprocess.run(['python3',str(out/'compile_display.py')],check=True)
cmd=json.loads((out/'backend-compile-command.json').read_text())
owner=[str(out/'OdinDisplayOwner.cpp') if v==str(out/'OdinLegacyGOPDisplay.cpp') else str(out/'OdinDisplayOwner.o') if v==str(out/'OdinLegacyGOPDisplay.o') else v for v in cmd]
(out/'owner-compile-command.json').write_text(json.dumps(owner,indent=2)+'\\n')
recipe=json.loads(Path('/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
r=subprocess.run(owner,cwd=recipe['directory'],capture_output=True,text=True)
(out/'owner-compile.log').write_text(r.stdout+r.stderr)
if r.returncode:raise SystemExit(r.stdout+r.stderr)
keyevents=[v.replace('OdinLegacyGOPDisplay.cpp','OdinKeyStoreEvents.cpp').replace('OdinLegacyGOPDisplay.o','OdinKeyStoreEvents.o') for v in cmd]
(out/'keyevents-compile-command.json').write_text(json.dumps(keyevents,indent=2)+'\\n')
r=subprocess.run(keyevents,cwd=recipe['directory'],capture_output=True,text=True)
(out/'keyevents-compile.log').write_text(r.stdout+r.stderr)
if r.returncode:raise SystemExit(r.stdout+r.stderr)
obj=out/'OdinLegacyGOPDisplay.o';late=out/'OdinLegacyGOPDisplay.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',obj,late],check=True)
data=bytearray(late.read_bytes());info=macho(data)
assert not any(s['name']=='__mod_init_func' for g in info['segments'] for s in g['sections'])
at=next(a for c,a,_ in info['commands'] if c==2)
symoff,count,stroff,strsize=struct.unpack_from('<4I',data,at+8)
assert symoff+16*count<=len(data) and stroff+strsize<=len(data)
found=[]
for i in range(count):
    p=symoff+16*i
    ix,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,p)
    assert ix<strsize
    name=data[stroff+ix:data.index(0,stroff+ix,stroff+strsize)].decode()
    if name=='__GLOBAL__sub_I_OdinLegacyGOPDisplay.cpp':
        assert kind&0x0e==0x0e and section and not kind&0xe0
        found.append(p+4)
assert len(found)==1
data[found[0]]|=1
def text(blob):
    sec=next(s for g in macho(blob)['segments'] for s in g['sections'] if s['name']=='__text')
    return blob[sec['fileoff']:sec['fileoff']+sec['size']]
assert text(data)==text(obj.read_bytes())
late.write_bytes(data)
keyobj=out/'OdinKeyStoreEvents.o';keylate=out/'OdinKeyStoreEvents.late.o'
subprocess.run(['llvm-objcopy','--remove-section=__DATA,__mod_init_func',keyobj,keylate],check=True)
keydata=bytearray(keylate.read_bytes());ki=macho(keydata)
assert not any(s['name']=='__mod_init_func' for g in ki['segments'] for s in g['sections'])
at=next(a for c,a,_ in ki['commands'] if c==2)
so,n,st,ss=struct.unpack_from('<4I',keydata,at+8);found=[]
for index in range(n):
    at=so+index*16;ix,kind,section,desc,value=struct.unpack_from('<IBBHQ',keydata,at)
    assert ix<ss
    name=keydata[st+ix:keydata.index(0,st+ix,st+ss)].decode()
    if name=='__GLOBAL__sub_I_OdinKeyStoreEvents.cpp':
        assert kind&0x0e==0x0e and section and not kind&0xe0
        found.append(at+4)
assert len(found)==1
keydata[found[0]]|=1
assert text(keydata)==text(keyobj.read_bytes())
keylate.write_bytes(keydata)
cc=cmd[0]
subprocess.run([cc,'-target','arm64-apple-ios16.5','-c',str(out/'original-bindings.S'),'-o',str(out/'original-bindings.o')],check=True)
subprocess.run(['llvm-ar','rcs',str(out/'libOdinDisplay.a'),str(late),str(keylate),str(out/'OdinDisplayOwner.o'),str(out/'original-bindings.o')],check=True)
receipt=dict(compiled=True,late_init_text_unchanged=True,automatic_initializer_removed=True,linked=False,executed=False,desktop_verified=False,device_commands_executed=False,
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='owner-build-receipt.json'})
(out/'owner-build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\\n')
print('PASS: opt-in late display archive built; no phone commands')
'''
    (OUT/'build_vm.py').write_text(vm_script)
    run([*SCP,str(OUT/'compile_display.py'),str(OUT/'build_vm.py'),'odin@127.0.0.1:'+REMOTE+'/'])
    run([*SSH,'python3 '+REMOTE+'/build_vm.py'])
    run([*SCP,'odin@127.0.0.1:'+REMOTE+'/{libOdinDisplay.a,OdinDisplayOwner.o,OdinLegacyGOPDisplay.o,OdinLegacyGOPDisplay.late.o,OdinKeyStoreEvents.o,OdinKeyStoreEvents.late.o,owner-build-receipt.json,compile-receipt.json,backend-class-dwarf.txt,class-dwarf.txt,owner-compile-command.json,owner-compile.log,keyevents-compile-command.json,keyevents-compile.log,OdinDisplayABIAnnotation.o,compile-command.json,backend-compile-command.json,original-bindings.o}',str(OUT)])

if __name__=='__main__':main()
