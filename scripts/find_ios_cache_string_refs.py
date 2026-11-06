"""Find bounded AArch64 ADRP/ADD references in the exact unmodified cache."""
from pathlib import Path
import argparse,json,struct,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
from inspect_cache_objc_refs import pointer
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--image',required=True)
p.add_argument('--string',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
c=Cache(DEFAULT)
image=next(i for i in c.images if i.name.endswith(a.image))
needle=a.string.encode()+b'\0';targets=[]
for (_,name),(va,size) in image.sections.items():
    if name not in ('__cstring','__objc_methname'):continue
    data=c.read(va,size);at=data.find(needle)
    while at>=0:targets.append(va+at);at=data.find(needle,at+1)
assert targets
cfstrings=[]
for (_,name),(va,size) in image.sections.items():
    if name!='__cfstring':continue
    for at in range(va,va+size,32):
        if pointer(c,at+16) in targets:cfstrings.append(at)
all_targets=targets+cfstrings
refs=[]
for (seg,name),(va,size) in image.sections.items():
    if name!='__text':continue
    words=struct.unpack('<'+'I'*(size//4),c.read(va,size//4*4))
    for index,w in enumerate(words):
        if w&0x9f000000!=0x90000000:continue
        imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
        if imm&(1<<20):imm-=1<<21
        page=((va+4*index)&~4095)+(imm<<12)
        if not any(page==target&~4095 for target in all_targets):continue
        reg=w&31
        for n in range(index+1,min(len(words),index+9)):
            v=words[n]
            if v&0xffc00000==0x91000000 and v>>5&31==reg:
                address=page+((v>>10)&4095)
                if address in all_targets:refs.append(dict(adrp=hex(va+index*4),add=hex(va+n*4),string_address=hex(address)))
record=dict(image=image.name,string=a.string,targets=list(map(hex,targets)),cfstrings=list(map(hex,cfstrings)),references=refs)
out=ROOT/'work/UniXNU-odin/build/display-analysis-ios16'/a.output
assert out.resolve().parent==(ROOT/'work/UniXNU-odin/build/display-analysis-ios16').resolve()
out.write_text(json.dumps(record,indent=2)+'\n');c.close()
print(json.dumps(record,indent=2))
