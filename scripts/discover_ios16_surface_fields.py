"""Find exact original IOSurface property readers; no iPadOS layout reuse."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
blob=(DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
image=np.macho(blob)
plan=json.loads((DEV/'build/ios16-prelink-u12match/prelink-emission-report.json').read_text())
assert hashlib.sha256(blob).hexdigest()==plan['candidate_sha256']
ext={e['segment']:e for e in plan['extents'] if e['module']=='com.apple.iokit.IOSurface'}
def read(va,n):
    at=np.backed_offset(image['segments'],va,n,len(blob));return blob[at:at+n]
text=ext['__TEXT_EXEC'];code=read(text['va'],text['size'])
strings=ext['__TEXT'];raw=read(strings['va'],strings['size'])
properties={}
for key in ('IOSurfaceWidth','IOSurfaceHeight','IOSurfaceBytesPerRow','IOSurfaceAllocSize','IOSurfacePixelFormat','IOSurfacePlaneInfo'):
    needle=key.encode()+b'\0';start=0
    while (at:=raw.find(needle,start))>=0:
        properties[strings['va']+at]=key;start=at+len(needle)
refs=[]
for off in range(0,len(code)-8,4):
    a,b=struct.unpack_from('<II',code,off)
    if a&0x9f000000!=0x90000000 or b&0xffc00000!=0x91000000 or a&31!=(b>>5)&31:continue
    imm=((a>>5&0x7ffff)<<2)|(a>>29&3)
    if imm&0x100000:imm-=0x200000
    pc=text['va']+off;target=(pc&~4095)+(imm<<12)+(b>>10&4095)
    if target in properties:refs.append(dict(key=properties[target],pc=hex(pc),string=hex(target),register=b&31))
out=dict(source_sha256=plan['candidate_sha256'],target='iOS16.5/20F66',property_references=refs,
    text_extent=text,field_semantics_qualified=False,device_commands_executed=False)
(DEV/'build/display-analysis-ios16/u25-surface-property-references.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(refs,indent=2))
