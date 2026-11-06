"""Qualify the new slot188 contract against exact original code and panic."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
b=(DEV/'build/display-owner-u15/kernel.prelinked.experimental.macho').read_bytes();m=np.macho(b)
def read(a,n):
    p=np.backed_offset(m['segments'],a,n,len(b));return b[p:p+n]
def word(a):return struct.unpack('<I',read(a,4))[0]
protocol=json.loads((DEV/'build/display-analysis-ios16/protocol-static-audit.json').read_text())
assert protocol['methods'][28]==dict(selector=28,action='0xfffffff004c02a40',scalar_input_count=0,
    structure_input_bytes=0,scalar_output_count=1,structure_output_bytes=0)
def branch_target(pc):
    v=word(pc);assert v&0xfc000000==0x94000000
    i=v&0x3ffffff
    if i&0x2000000:i-=0x4000000
    return pc+4*i
assert branch_target(0xfffffff004c02a70)==0xfffffff004c007f4
# This wrapper obtains the original provider then calls vtable byte1504 / 8.
assert word(0xfffffff004c0080c)==0xf9400000 | (216//8)<<10 | 8<<5
assert word(0xfffffff004c00818)==0xf9400000 | (1504//8)<<10 | 8<<5 | 8
assert word(0xfffffff004c1f178)==0xf9400000 | (5096//8)<<10 | 8<<5
assert word(0xfffffff004c1f17c)==0xf9400008
address=(0xfffffff004c1f184&~4095)-13307904+2253
assert read(address,10)==b'dot-pitch\0'
# Original property-missing branch: mov w8,#0x2f0; movk w8,#0xe000,lsl#16.
assert word(0xfffffff004c1f234)==0x52800000 | 0x2f0<<5 | 8
assert word(0xfffffff004c1f238)==0x72a00000 | 0xe000<<5 | 8
assert word(0xfffffff004c1f24c)==0xb9000128  # str w8,[x9]: uint32 output
panic=json.loads((DEV/'build/qemu-early-entry-u15desktop/panic.json').read_text())
assert panic['slots'][1:3]==[0xfffffff004c1f17c,0xfffffff004c00820]
result=dict(passed=True,scope='Original iOS16.5 instruction and actual QEMU panic qualification',
    selector=28,provider_slot=188,prototype='IOReturn getDotPitch(uint32_t *)',
    original_method='0xfffffff004c1f128',original_device_field=5096,
    property='dot-pitch',missing_property_return='0xe00002f0',output_bytes=4,
    original_null_dereference_runtime_verified=True,physical_density_available=False,
    repair_policy='Return the exact original missing-property result and zero output; no fake physical density',
    candidate_sha256=hashlib.sha256(b).hexdigest(),desktop_verified=False,device_commands_executed=False)
(DEV/'build/display-owner-u16/dot-pitch-qualification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
