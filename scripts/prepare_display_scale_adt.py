"""Configure logical scale at the actual iOS16 MobileGestalt input, before exec.

Only a computer replay ADT is emitted. No phone access or cache code changes.
"""
from pathlib import Path
import argparse,copy,hashlib,json,struct
from adt_codec import decode,encode,lookup
from inspect_cache_objc_refs import Cache,DEFAULT,cstring,pointer

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=DEV/'build/desktop-handoff-u13cryptex/kernel.macho.adt')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--scale',type=int,choices=(1,2,3),default=3)
a=p.parse_args();assert not a.output.exists()
c=Cache(DEFAULT)
assert cstring(c,pointer(c,0x1d5b59ff8+16))=='main-screen-scale'
assert c.read(0x188362d10,4)==struct.pack('<I',0x1e201000) # fmov s0, #2
assert c.resolve(0x19c5282c0)['symbol']=='_MGGetFloat32Answer'
assert cstring(c,0x19c580dd7)=='IODeviceTree:/chosen'
assert cstring(c,pointer(c,0x1d7366c00+16))=='display-scale'
# Collector supplies the chosen property to its exact typed u32 reader.
assert c.read(0x19c531cd8,20)==bytes.fromhex('e00314aa020080520300805224008052a76f0094')
# CFData is explicitly required to be four bytes and read natively as u32.
assert c.read(0x19c54dcb8,4)==struct.pack('<I',0xf100101f)
assert c.read(0x19c54dcc8,4)==struct.pack('<I',0xb9400013)
c.close()
source=a.source.read_bytes();tree=decode(source);before=copy.deepcopy(tree)
chosen=lookup(tree,'chosen')
for name,value in [('display-scale',a.scale),('display-rotation',0)]:
    assert name not in chosen
    chosen[name]=struct.pack('<I',value)
blob=encode(tree);a.output.parent.mkdir(exist_ok=True,parents=True);a.output.write_bytes(blob)
check=decode(blob)
for name in ('display-scale','display-rotation'):del lookup(check,'chosen')[name]
assert check==before and a.source.read_bytes()==source
record=dict(scope='Exact iOS16.5 reader-qualified computer replay configuration',
    source=str(a.source),source_sha256=hashlib.sha256(source).hexdigest(),
    output=str(a.output),sha256=hashlib.sha256(blob).hexdigest(),
    logical_scale=a.scale,rotation=0,logical_size=[1080/a.scale,2400/a.scale],
    all_other_tree_properties_unchanged=True,cache_code_modified=False,
    root_image_modified=False,device_commands_executed=False,desktop_verified=False,
    actual_reader='libMobileGestalt 0x19c531c94; chosen/display-scale -> native 4-byte u32')
a.output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
