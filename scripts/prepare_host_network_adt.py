"""Supply QEMU-only locally administered network inputs to original MobileGestalt.

This advertises no network controller and does not use phone identifiers.
The pinned ios-fuxi mkadt.py documents why missing inputs cause repeated waits.
Exact iOS16.5 readers are checked here before writing a separate ADT copy.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import struct
from adt_codec import decode, encode, lookup
from inspect_cache_objc_refs import Cache, DEFAULT, cstring, pointer

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
assert not a.output.exists() and a.source.resolve()!=a.output.resolve()
c=Cache(DEFAULT)
assert cstring(c,0x19c580dd7)=='IODeviceTree:/chosen'
checks={
    0x19c5471b4:'c00100b0005c3791', # x0: chosen path
    0x19c5471bc:'21711df021000691', # x1: Wi-Fi CFString
    0x19c53c048:'61711dd021002f91', # x1: Bluetooth CFString
}
# Store exact observed bytes as evidence, then qualify the property bindings,
# common CFData helper, and immediate success branches independently.
for obj,key in ((0x1d736e180,'mac-address-wifi0'),
                (0x1d736abc0,'mac-address-bluetooth0')):
    assert cstring(c,pointer(c,obj+16))==key
def branch_target(at):
    word=struct.unpack('<I',c.read(at,4))[0]
    assert word&0xfc000000==0x94000000
    imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    return at+4*imm
assert branch_target(0x19c5471c8)==branch_target(0x19c53c054)==0x19c52c5a8
assert c.read(0x19c5471cc,4)==struct.pack('<I',0xb50001a0)
assert c.read(0x19c53c058,4)==struct.pack('<I',0xb50000a0)
def original_stub_target(at):
    adrp,add,branch=struct.unpack('<3I',c.read(at,12))
    assert adrp&0x9f00001f==0x90000010
    assert add&0xffc003ff==0x91000210 and branch==0xd61f0200
    imm=((adrp>>29)&3)|(((adrp>>5)&0x7ffff)<<2)
    if imm&(1<<20):imm-=1<<21
    return (at&~4095)+(imm<<12)+((add>>10)&4095)
assert c.resolve(original_stub_target(branch_target(0x19c52c5cc)))['symbol']=='_CFDataGetTypeID'
assert c.resolve(original_stub_target(branch_target(0x19c52c5c4)))['symbol']=='_CFGetTypeID'
observed={hex(at):c.read(at,len(bytes.fromhex(value))).hex() for at,value in checks.items()}
assert observed=={hex(at):value for at,value in checks.items()}
c.close()
source=a.source.read_bytes();tree=decode(source);before=copy.deepcopy(tree)
props=lookup(tree,'chosen')
values={'mac-address-wifi0':bytes.fromhex('020000835001'),
        'mac-address-bluetooth0':bytes.fromhex('020000835002')}
for key,value in values.items():
    assert key not in props and len(value)==6 and value[0]&3==2
    props[key]=value
blob=encode(tree);check=decode(blob)
for key in values:del lookup(check,'chosen')[key]
assert check==before and a.source.read_bytes()==source
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(blob)
record=dict(scope='Computer-only QEMU network-address inputs; not phone hardware configuration',
    reference='bangprovn/ios-fuxi@27f6a31c8b27c6f9127f9cf27092968422579ccf/tools/mkadt.py',
    source=str(a.source),source_sha256=hashlib.sha256(source).hexdigest(),
    sha256=hashlib.sha256(blob).hexdigest(),property_lengths={k:len(v) for k,v in values.items()},
    exact_original_references=observed,cfdata_helper='0x19c52c5a8',
    all_other_properties_preserved=True,security_properties_modified=False,
    executable_modified=False,device_commands_executed=False,runtime_verified=False)
a.output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
