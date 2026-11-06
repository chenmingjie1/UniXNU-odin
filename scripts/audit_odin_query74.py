"""Qualify only the wire signature of original selector74 / abstract slot212."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
b=(DEV/'build/display-owner-u16/kernel.prelinked.experimental.macho').read_bytes();m=np.macho(b)
def word(a):
    p=np.backed_offset(m['segments'],a,4,len(b));return struct.unpack_from('<I',b,p)[0]
def ldr(rt,rn,off):return 0xf9400000 | (off//8)<<10 | rn<<5 | rt
p=json.loads((DEV/'build/display-analysis-ios16/protocol-static-audit.json').read_text())
assert p['methods'][74]==dict(selector=74,action='0xfffffff004c02c04',scalar_input_count=1,
    structure_input_bytes=0,scalar_output_count=1,structure_output_bytes=64)
# Selector action forwards scalarInput[0], scalarOutput and structureOutput.
assert word(0xfffffff004c02c24)==ldr(8,8,32)
assert word(0xfffffff004c02c34)==ldr(2,8,72)
assert word(0xfffffff004c02c3c)==ldr(3,8,88)
call=word(0xfffffff004c02c40);assert call&0xfc000000==0x94000000
imm=call&0x3ffffff
if imm&0x2000000:imm-=0x4000000
assert 0xfffffff004c02c40+imm*4==0xfffffff004c00c14
# Wrapper supplies its own uint32 temporary in x2, output struct in x3.
assert word(0xfffffff004c00c34)==0x91000000 | 12<<10 | 31<<5 | 2
assert word(0xfffffff004c00c48)==ldr(0,8,216)
assert word(0xfffffff004c00c50)==ldr(3,31,16)
assert word(0xfffffff004c00c58)==ldr(8,8,212*8)
assert word(0xfffffff004c00c64)==0xb9400fe8  # ldr w8,[sp,#12]
assert word(0xfffffff004c00c6c)==0xf9000128  # scalar wire widening
panic=json.loads((DEV/'build/qemu-early-entry-u16dotpitchfixed/panic.json').read_text())
assert panic['slots'][:2]==[212,0xfffffff004c00c60]
result=dict(passed=True,scope='Exact original client ABI and observed call; contents deliberately unimplemented',
    selector=74,provider_slot=212,input_uint32=True,output_uint32=True,structure_output_bytes=64,
    prototype='IOReturn queryOutput64(uint32_t,uint32_t *,void *)',contents_qualified=False,
    implementation='Zero bounded outputs and return kIOReturnUnsupported; never report invented capabilities',
    original_abstract_trap_observed=True,candidate_sha256=hashlib.sha256(b).hexdigest(),
    desktop_verified=False,device_commands_executed=False)
(DEV/'build/display-owner-u17/query74-qualification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
