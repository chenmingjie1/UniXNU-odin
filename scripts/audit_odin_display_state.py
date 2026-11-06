"""Qualify original iOS16 logical display power setter, dispatch and wait gate."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
path=DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho'
blob=path.read_bytes();image=np.macho(blob)
discovery=json.loads((DEV/'build/display-analysis-ios16/dispatch-discovery.json').read_text())
assert hashlib.sha256(blob).hexdigest()==discovery['candidate_sha256']
legacy=next(t for t in discovery['dispatch_candidates'] if t.get('name')=='IOMobileFramebufferLegacy')
def read(va,n):
    at=np.backed_offset(image['segments'],va,n,len(blob));return blob[at:at+n]
def w(va):return struct.unpack('<I',read(va,4))[0]
def load(va,op,reg,base,offset,scale):
    v=w(va);assert v&0xffc00000==op and v&31==reg and v>>5&31==base and (v>>10&4095)*scale==offset,hex(va)
assert legacy['methods'][336]['address']=='0xfffffff004c1e1d8'
load(0xfffffff004c1e20c,0x39400000,8,8,16,1)
load(0xfffffff004c1e220,0xb9400000,8,8,0,4)
load(0xfffffff004c1e23c,0xb9400000,8,8,4,4)
load(0xfffffff004c1e240,0xb9400000,9,9,5236,4)
load(0xfffffff004c1e260,0xb9000000,8,9,5236,4)
load(0xfffffff004c1e274,0xb9400000,8,8,8,4)
load(0xfffffff004c1e290,0xb9400000,8,8,12,4)
load(0xfffffff004c1e294,0xb9400000,9,9,5240,4)
load(0xfffffff004c1e2b4,0xb9000000,8,9,5240,4)
load(0xfffffff004c1e2d8,0xf9400000,8,8,284*8,8)
assert w(0xfffffff004c1e2dc)==0xd63f0100
assert legacy['methods'][284]['address']=='0xfffffff004c26ac8'
assert w(0xfffffff004c26ad0)==0x52800000 and w(0xfffffff004c26ad8)==0xd65f03c0
assert legacy['methods'][176]['address']=='0xfffffff004c150d8'
load(0xfffffff004c15198,0xb9400000,10,8,5240,4)
record=dict(passed=True,target_os='iOS16.5 / 20F66',original_slot=336,
    request_bytes=20,fields=dict(skip_display=0,display=4,skip_power=8,power=12,suppress_apply=16),
    state_fields=dict(display=5236,logical_power=5240),
    readiness_request=[1,0,0,1,1],default_apply_returns_success=True,
    original_wait_checks_logical_power=True,
    original_method_sha256=hashlib.sha256(read(0xfffffff004c1e1d8,300)).hexdigest(),
    source_candidate_sha256=discovery['candidate_sha256'],
    scope='Logical readiness of a real mapped GOP buffer, no hardware power or vblank assertion',
    runtime_verified=False,desktop_verified=False,device_commands_executed=False)
out=DEV/'build/display-owner-u19/state-request-qualification.json'
out.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
