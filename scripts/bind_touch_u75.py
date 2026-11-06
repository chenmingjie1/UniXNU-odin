"""Bind only the measured original iOS16 HID methods, then relink source XNU."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin';OUT=DEV/'build/touch-metal-u75'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
from build_odin_display_owner import SSH,SCP
SSH[SSH.index('-i')+1]=str(DEV/'build/touch-metal-u74/guest-ssh-key');SCP[SCP.index('-i')+1]=str(DEV/'build/touch-metal-u74/guest-ssh-key')
remote='/home/odin/unixnu-odin-build/evidence/odin-touch-u75'
b=(OUT/'OdinStTouch.o').read_bytes();m=np.macho(b);at=next(a for c,a,_ in m['commands'] if c==2)
sy,count,strings,ss=struct.unpack_from('<4I',b,at+8)
symbols=[]
for i in range(count):
 ix,kind,section,desc,va=struct.unpack_from('<IBBHQ',b,sy+i*16)
 symbols.append((b[strings+ix:b.index(0,strings+ix)].decode(),va,kind))
vt=next(va for n,va,_ in symbols if n=='__ZTV11OdinStTouch');relocations={}
for g in m['segments']:
 for sec in g['sections']:
  if sec['va']<=vt<sec['va']+sec['size']:
   ro,rc=struct.unpack_from('<2I',b,sec['command_offset']+56)
   for i in range(rc):
    offset,bits=struct.unpack_from('<2I',b,ro+i*8)
    if bits>>27&1 and bits>>28==0 and bits>>25&3==3:relocations[sec['va']+offset]=symbols[bits&0xffffff][0]
compiled=[relocations.get(vt+16+i*8) for i in range(207)]
assert all(compiled) and vt+16+207*8 not in relocations
t=json.loads((DEV/'build/hid-analysis-ios16/dispatch-discovery.json').read_text())['classes'][0]
assert t['entries']==207 and t['instance_bytes']==208 and t['abstract_slots']==[180]
blob=(DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes();image=np.macho(blob)
names={n:a for a,ns in np.exports(blob,image).items() for n in ns}
def read(va,n):
 at=np.backed_offset(image['segments'],va,n,len(blob));return blob[at:at+n]
ctor=int(t['constructor_candidates'][0],16)
assert read(ctor,8)==bytes.fromhex('fd7bbfa9fd030091')
words=struct.unpack('<12I',read(ctor,48));end=words.index(0xd65f03c0)
assert end==7 and words[end+1]&0xfc000000==0x14000000
bindings={'__ZN11IOHIDDeviceC2EPK11OSMetaClass':ctor,'__ZN11IOHIDDeviceD2Ev':ctor+(end+1)*4,'__ZN11IOHIDDevice10gMetaClassE':int(t['metaclass'],16),'__ZTV11IOHIDDevice':int(t['vtable'],16)}
owned=[]
for i,name in enumerate(compiled):
 if name.startswith(('__ZN11OdinStTouch','__ZNK11OdinStTouch')):owned.append(i)
 elif '11IOHIDDevice' in name:bindings[name]=int(t['methods'][i]['address'],16)
 else:assert i<168 and names.get(name)==int(t['methods'][i]['address'],16),(i,name)
assert owned==[0,1,7,14,86,87,111,171,173,180],owned
undefined={n for n,_,k in symbols if k==1 and '11IOHIDDevice' in n}
assert undefined==set(bindings),(undefined-set(bindings),set(bindings)-undefined)
(OUT/'hid-original-bindings.S').write_text(''.join(f'.globl {n}\n.set {n}, {a:#x}\n' for n,a in sorted(bindings.items())))
audit=dict(target='iOS16.5/20F66',original_slots=207,original_size=208,owned_slots=owned,bindings={n:hex(a) for n,a in bindings.items()},object_sha256=hashlib.sha256(b).hexdigest(),runtime_qualified=False)
(OUT/'hid-interface-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
subprocess.run([*SCP,str(OUT/'hid-original-bindings.S'),str(DEV/'scripts/link_touch_u75_guest.py'),'odin@127.0.0.1:'+remote+'/'],check=True)
subprocess.run([*SSH,'python3 '+remote+'/link_touch_u75_guest.py'],check=True)
subprocess.run([*SCP,'odin@127.0.0.1:'+remote+'/native-real-iig.macho',str(OUT)],check=True)
subprocess.run([sys.executable,str(DEV/'scripts/prepare_ios16_prelink.py'),'--kernel',str(OUT/'native-real-iig.macho'),'--output-dir',str(OUT),'--driver-policy',str(DEV/'configs/original-driver-policy.toml')],check=True)
subprocess.run([sys.executable,str(DEV/'scripts/audit_ios16_prelink.py'),'--input-dir',str(OUT)],check=True)
