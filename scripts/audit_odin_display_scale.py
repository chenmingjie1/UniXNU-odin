"""Qualify the zero-scale failure using real captured objects and exact code."""
from pathlib import Path
import hashlib,json,re,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
RUN=DEV/'build/qemu-early-entry-u17trapdetail'
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
c=Cache(DEFAULT)
state=json.loads((RUN/'user-trap.json').read_text())
obj=(RUN/'user-trap-X19.bin').read_bytes()
width,height,preferred,override,refresh,gamut,hdr,rotation,virtual=struct.unpack_from('<3Q2d3qB',obj,8)
assert (width,height,preferred,override,refresh,gamut,hdr,rotation,virtual)==(1080,2400,0,0.0,60.0,1,0,0,0)
selector=(RUN/'user-trap-X20.bin').read_bytes().split(b'\0')[0].decode()
assert selector=='_initWithWidth:height:preferredScale:scaleOverride:refreshRate:gamut:hdr:rotation:virtual:validityCheck:'
pc=int(state['registers']['PC'],16);unslid=0x19b8f5b10;slide=pc-unslid
trace=(RUN/'trace.log').read_text()
assert c.read(unslid-4,8)==bytes.fromhex('930db195000020d4')
assert f'{pc-4:#x}:  95b10d93  bl ' in trace
anchor=re.search(r'^(0x[0-9a-f]+):  f0279d68  adrp',trace,re.M)
assert anchor and c.read(int(anchor[1],16)-slide,12)==bytes.fromhex('689d27f0008104f9c0035fd6')
# Actual validity path: preferred scale 0 enters a fallback-scale check;
# the exact BaseBoard leaf is BSFloatIsZero, not an inferred NaN predicate.
assert c.read(0x19b8f59b8,4)==struct.pack('<I',0xb40000d8)
assert c.read(0x19b8f59e8,4)==struct.pack('<I',0x37000140)
assert c.resolve(0x18dd39d40)['symbol']=='_BSFloatIsZero'
# Match the actual zero test and return (literal materialization is decoded in
# the preserved LLVM disassembly rather than guessing its immediate encoding).
assert c.read(0x18dd39d40,4)==bytes.fromhex('00c0601e')
assert c.read(0x18dd39d54,4)==bytes.fromhex('c0035fd6')
refs=json.loads((DEV/'build/display-analysis-ios16/u18-scale-env-refs.json').read_text())
assert refs['references']==[dict(adrp='0x1884e29a0',add='0x1884e29a4',string_address='0x188592b95')]
assert c.read(0x188592b95,22)==b'CA_MAIN_DISPLAY_SCALE\0'
record=dict(passed=True,scope='Measured computer EL0 failure and exact unchanged cache',
    kernel_sha256=json.loads((RUN/'verification.json').read_text())['kernel_sha256'],
    cache_slide=hex(slide),user_pc=hex(pc),selector=selector,
    actual_mode=dict(width=width,height=height,preferred_scale=preferred,scale_override=override,
                    refresh_hz=refresh,gamut=gamut,hdr=hdr,rotation=rotation,virtual=virtual),
    failed_condition='preferredScale == 0 and BSFloatIsZero(scaleOverride)',
    explicit_configuration=dict(variable='CA_MAIN_DISPLAY_SCALE',value='3',logical_size=[360,800],
        scope='Logical UI scale only; does not assert panel physical density'),
    desktop_verified=False,device_commands_executed=False,
    evidence_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.glob('user-trap*') if p.is_file()})
c.close();out=DEV/'build/display-analysis-ios16/u18-scale-qualification.json'
out.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
