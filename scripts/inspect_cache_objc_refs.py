"""Read exact arm64 cache rebases and ObjC selector-reference stubs."""
from pathlib import Path
import argparse,json,struct,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT

def pointer(c,address):
    value=struct.unpack('<Q',c.read(address,8))[0]
    if not value:return 0
    for _,data in c.files:
        off,count=struct.unpack_from('<II',data,312)
        for index in range(count):
            m=struct.unpack_from('<6Q2I',data,off+index*56)
            if m[0]<=address<m[0]+m[1] and m[4]:
                assert struct.unpack_from('<I',data,m[3])[0]==2
                mask,base=struct.unpack_from('<QQ',data,m[3]+24)
                return (value&(~mask&((1<<64)-1)))+base
    return value

def cstring(c,address):
    data=bytearray()
    while len(data)<512:
        block=c.read(address,min(512-len(data),4096-(address&4095)))
        end=block.find(b'\0')
        if end>=0:
            data.extend(block[:end])
            return data.decode('utf8')
        data.extend(block);address+=len(block)
    raise ValueError('Unterminated cache string within 512 bytes')

def stub(c,address):
    adrp,ldr=struct.unpack('<II',c.read(address,8))
    assert adrp&0x9f00001f==0x90000001 and ldr&0xffc003ff==0xf9400021
    imm=((adrp>>29)&3)|(((adrp>>5)&0x7ffff)<<2)
    if imm&(1<<20):imm-=1<<21
    ref=(address&~4095)+(imm<<12)+((ldr>>10)&4095)*8
    target=pointer(c,ref)
    return dict(stub=hex(address),reference=hex(ref),target=hex(target),selector=cstring(c,target))

def classes(c,image_suffix,names):
    image=next(i for i in c.images if i.name.endswith(image_suffix))
    region=struct.unpack_from('<Q',c.files[0][1],224)[0]
    opt=region+struct.unpack_from('<Q',c.files[0][1],464)[0]
    assert struct.unpack('<I',c.read(opt,4))[0]==1
    selector_base=region+struct.unpack('<Q',c.read(opt+48,8))[0]
    result=[]
    for (_,section),(va,size) in image.sections.items():
        if section!='__objc_classlist':continue
        for at in range(va,va+size,8):
            cl=pointer(c,at)
            ro=pointer(c,cl+32)&~7
            name=cstring(c,pointer(c,ro+24))
            if name not in names:continue
            methods=pointer(c,ro+32)
            flags,count=struct.unpack('<II',c.read(methods,8))
            rows=[];stride=flags&0xfffc
            assert count<10000 and stride in (12,24)
            for i in range(count):
                entry=methods+8+i*stride
                if flags&0x80000000:
                    offsets=struct.unpack('<3i',c.read(entry,12))
                    if flags&0x40000000:
                        sel=selector_base+struct.unpack('<I',c.read(entry,4))[0]
                    else:sel=pointer(c,entry+offsets[0])
                    imp=entry+8+offsets[2]
                    types=entry+4+offsets[1]
                else:sel,types,imp=(pointer(c,entry+8*j) for j in range(3))
                rows.append(dict(selector=cstring(c,sel),types=cstring(c,types),implementation=hex(imp)))
            result.append(dict(name=name,address=hex(cl),methods=rows))
    assert len(result)==len(names),(names,[r['name'] for r in result])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stub',action='append',type=lambda v:int(v,0),default=[])
    p.add_argument('--pointer',action='append',type=lambda v:int(v,0),default=[])
    p.add_argument('--image')
    p.add_argument('--class-name',action='append',default=[])
    p.add_argument('--output',type=Path)
    a=p.parse_args();c=Cache(DEFAULT)
    result=[stub(c,x) for x in a.stub]+[dict(address=hex(x),target=hex(pointer(c,x)),text=cstring(c,pointer(c,x))) for x in a.pointer]
    if a.class_name:result+=classes(c,a.image,a.class_name)
    text=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.write_text(text)
    print(text)
    c.close()
