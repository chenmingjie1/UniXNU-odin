"""Qualify exact iOS16 surface accessors using original property stores."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
blob=(DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
im=np.macho(blob);discovery=json.loads((DEV/'build/display-analysis-ios16/dispatch-discovery.json').read_text())
assert hashlib.sha256(blob).hexdigest()==discovery['candidate_sha256']
def read(at,n):
    off=np.backed_offset(im['segments'],at,n,len(blob));return blob[off:off+n]
def word(at):return struct.unpack('<I',read(at,4))[0]
def access(at,op,reg,base,offset,scale):
    w=word(at)
    assert w&0xffc00000==op and w&31==reg and w>>5&31==base and (w>>10&4095)*scale==offset,hex(at)
def property_ref(at,key):
    a,b=struct.unpack('<2I',read(at,8))
    assert a&0x9f00001f==0x90000001 and b&0xffc003ff==0x91000021
    imm=((a>>5&0x7ffff)<<2)|(a>>29&3)
    if imm&0x100000:imm-=0x200000
    addr=(at&~4095)+(imm<<12)+(b>>10&4095)
    assert read(addr,len(key)+1)==key.encode()+b'\0'
getters={}
for name,field,getter,reference,store,key in [
    ('width',144,0xfffffff004a507ec,0xfffffff004a4cc10,0xfffffff004a4cc40,'IOSurfaceWidth'),
    ('height',148,0xfffffff004a507f4,0xfffffff004a4cc58,0xfffffff004a4cc88,'IOSurfaceHeight'),
    ('stride',152,0xfffffff004a50804,0xfffffff004a4cf30,0xfffffff004a4cf64,'IOSurfaceBytesPerRow'),
    ('format',164,0xfffffff004a507bc,0xfffffff004a4c9b0,0xfffffff004a4c9d8,'IOSurfacePixelFormat'),
    ('allocation',172,0xfffffff004a5082c,0xfffffff004a4d2cc,0xfffffff004a4d3b4,'IOSurfaceAllocSize')]:
    property_ref(reference,key);access(store,0xb9000000,0,19,field,4)
    access(getter,0xb9400000,0,0,field,4);assert word(getter+4)==0xd65f03c0
    getters[name]=dict(field=field,address=hex(getter),property=key,property_reader=hex(reference),store=hex(store))
# Original IOSurface prepares, reads, and completes the object at +56 using
# the source IOMemoryDescriptor call slots. +48 is an IOMemoryMap, not backing.
access(0xfffffff004a4f274,0xf9400000,0,19,56,8)
access(0xfffffff004a4f27c,0xf9400000,8,8,216,8)
access(0xfffffff004a4f29c,0xf9400000,20,19,56,8)
access(0xfffffff004a4f2a4,0xf9400000,8,8,176,8)
access(0xfffffff004a4f2cc,0xf9400000,0,19,56,8)
access(0xfffffff004a4f2d4,0xf9400000,8,8,224,8)
access(0xfffffff004c170c0,0xf9400000,8,8,200,8) # source descriptor readBytes
access(0xfffffff004a50714,0xf9400000,0,0,56,8);assert word(0xfffffff004a50718)==0xd65f03c0
getters['descriptor']=dict(field=56,address='0xfffffff004a50714',qualified_by='original prepare/getLength/complete calls')
# Plane count has a distinct getter and controls the original nonplanar path.
access(0xfffffff004a4d328,0xb9400000,10,19,176,4)
assert word(0xfffffff004a4d32c)==0x3400036a # cbz w10, nonplanar
access(0xfffffff004a50824,0xb9400000,0,0,176,4);assert word(0xfffffff004a50828)==0xd65f03c0
getters['planes']=dict(field=176,address='0xfffffff004a50824',qualified_by='original planar/nonplanar branch')
access(0xfffffff004c185b4,0xf9400000,8,8,282*8,8)
assert word(0xfffffff004c185b8)==0xd63f0100 and word(0xfffffff004c185c0)==0x0a080008
# The four IOSurface slots are constructed and retained by the original family.
assert word(0xfffffff004c17274)==0x9122214a
windows=[(0xfffffff004a4cc08,132),(0xfffffff004a4cf28,64),(0xfffffff004a4c9a8,56),
    (0xfffffff004a4d2c4,244),(0xfffffff004a4f274,108),(0xfffffff004a50714,8),
    (0xfffffff004c185a8,32),(0xfffffff004c17264,56)]
record=dict(passed=True,target='iOS16.5/20F66',source_sha256=discovery['candidate_sha256'],
    getters=getters,validator_slot=282,validator_prototype='bool(this,const void *request)',
    surface_slots=dict(offset=2184,count=4),
    instruction_windows=[dict(address=hex(at),size=n,sha256=hashlib.sha256(read(at,n)).hexdigest()) for at,n in windows],
    device_commands_executed=False,desktop_verified=False)
out=DEV/'build/display-analysis-ios16/u25-surface-contract.json';out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
