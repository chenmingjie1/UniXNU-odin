"""Identify actual replay traps from instructions, including per-run cache ASLR."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,re,struct,sys
ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',default='u17query74')
a=p.parse_args();assert a.tag.isalnum()
RUN=DEV/('build/qemu-early-entry-'+a.tag)
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
c=Cache(DEFAULT)
trace=(RUN/'trace.log').read_text()
pcs=[int(x,16) for x in re.findall(r'Taking exception 7 \[Breakpoint\].*?ELR (0x[0-9a-f]+)',trace,re.S)]
assert len(set(pcs))==1
pc=pcs[0]
prev=re.search(rf'^{pc-4:#x}:  ([0-9a-f]{{8}})  bl ',trace,re.M)
assert prev and f'{pc:#x}:  d4200000  brk' in trace
needle=struct.pack('<II',int(prev[1],16),0xd4200000)
hits=[]
for lo,hi,fo,data in c.maps:
    at=data.find(needle,fo,fo+hi-lo)
    while at>=0:
        hits.append(lo+at-fo+4)
        at=data.find(needle,at+1,fo+hi-lo)
assert len(hits)==1
slide=pc-hits[0]
assert slide>=0 and not slide%4096
anchor=re.search(r'^(0x[0-9a-f]+):  f0279d68  adrp.*?\n0x[0-9a-f]+:  f9048100  str.*?\n0x[0-9a-f]+:  d65f03c0  ret',trace,re.M)
assert anchor and c.read(int(anchor[1],16)-slide,12)==bytes.fromhex('689d27f0008104f9c0035fd6')

def cfstring(address):
    pointer,length=struct.unpack_from('<QQ',c.read(address,32),16)
    assert 0<length<=4096
    for lo,hi,fo,data in c.maps:
        if lo<=address<hi:
            off,count=struct.unpack_from('<II',data,312)
            for i in range(count):
                m=struct.unpack_from('<6Q2I',data,off+i*56)
                if m[0]<=address<m[0]+m[1]:
                    assert struct.unpack_from('<I',data,m[3])[0]==2
                    mask,base=struct.unpack_from('<QQ',data,m[3]+24)
                    p=(pointer&(~mask&((1<<64)-1)))+base
                    return c.read(p,length).decode('utf8')
    raise AssertionError(hex(address))

# Exact CFString references in the newly reached FrontBoard assertion routine.
strings={hex(a):cfstring(a) for a in (0x1d716c8e0,0x1d716c920)}
record=dict(scope='Computer-only exact instruction and cache analysis',
    kernel_sha256=json.loads((RUN/'verification.json').read_text())['kernel_sha256'],
    trace_sha256=hashlib.sha256((RUN/'trace.log').read_bytes()).hexdigest(),
    cache_slide=hex(slide),independent_anchor=anchor[1],
    breakpoint_count=len(pcs),runtime_pc=hex(pc),resolved=c.resolve(hits[0]),
    assertion_literals=strings,old_main_display_assertion_observed=False,
    framebuffer='Kernel/user log text only, visually inspected; no desktop',
    desktop_verified=False,device_commands_executed=False)
c.close()
(RUN/'display-runtime-analysis.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
