"""Qualify exact original queue operations and a real first compositor request."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
DEV=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',default='u31-queue-contract.json')
a=p.parse_args()
assert Path(a.output).name==a.output and a.output.endswith('.json')
sys.path.insert(0,str(DEV.parent/'UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
discovery=json.loads((DEV/'build/display-analysis-ios16/dispatch-discovery.json').read_text())
blob=(DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
assert hashlib.sha256(blob).hexdigest()==discovery['candidate_sha256']
image=np.macho(blob)
def read(at,n):
    off=np.backed_offset(image['segments'],at,n,len(blob));return blob[off:off+n]
def word(at):return struct.unpack('<I',read(at,4))[0]
# Exact original selection and completion, in the unchanged iOS16 executable.
checks={
    0xfffffff004c11548:0xf81f83a0, # this, request, uint32 state arguments
    0xfffffff004c1154c:0xf81f03a1,
    0xfffffff004c11550:0xb81ec3a2,
    0xfffffff004c11ecc:0xf9498928, # ready head -> current
    0xfffffff004c11ed0:0xf9098528,
    0xfffffff004c11ee4:0xf944b508, # request next at 2408
    0xfffffff004c11f08:0xf944b508,
    0xfffffff004c11f0c:0xf944b908, # next->previous at 2416
    0xfffffff004c11e50:0xf9498d28, # ready tail pointer
    0xfffffff004c11e70:0xf9098d28,
    0xfffffff004c1203c:0x52800062, # original activating state 3
    0xfffffff004c12770:0xf909851f, # original completion clears current
    0xfffffff004c18ef8:0xd2826409, # pending head address: this +4896
    0xfffffff004c18f04:0xd2826209, # ready head address: this +4880
    0xfffffff004c18f14:0x94001e09, # move helper before backend kick
    0xfffffff004c19000:0xf9445108, # slot276 queue kick
    0xfffffff004c12240:0xf9450508, # slot321 completion reports
    0xfffffff004c16d00:0xb9034948, # packet option -> request 840
    0xfffffff004c16d04:0xf9401d28,
}
# Assert independently matched instruction values, not generated ABI text.
for at,expected in checks.items():assert word(at)==expected,(hex(at),hex(word(at)),hex(expected))
legacy=next(c for c in discovery['dispatch_candidates'] if c.get('name')=='IOMobileFramebufferLegacy')
assert legacy['methods'][276]['address']=='0xfffffff004c1b2b8'
assert legacy['methods'][281]['address']=='0xfffffff004c1cce4' and 321 in legacy['abstract_slots']
assert word(0xfffffff004c1cd00)==0x97ffd50b # original completeCurrentSwap -> completion(true)
run=DEV/'build/qemu-early-entry-u30requestabi'
v=json.loads((run/'verification.json').read_text())
assert v['hardware_breakpoint_reached']
request=(run/'register-memory-X01.bin').read_bytes()
assert len(request)==2432
assert struct.unpack_from('<4I',request,17)==struct.unpack_from('<4I',request,81)==(0,0,1080,2400)
assert struct.unpack_from('<3I',request,792)==(0x80000007,0x80000006,0xff000000)
assert struct.unpack_from('<2I',request,816)==(1080,2400)
assert struct.unpack_from('<3I',request,804)==(0,0,0)
assert struct.unpack_from('<5I',request,824)==(0,0,0,0,0)
result=dict(passed=True,target='iOS16.5/20F66',source_sha256=discovery['candidate_sha256'],
    original_instruction_checks={hex(at):hex(value) for at,value in checks.items()},
    request_state_helper='0xfffffff004c11538',
    controller_fields=dict(current=4872,ready_head=4880,ready_tail=4888,pending_head=4896,pending_tail=4904),
    submission_move_helper='0xfffffff004c20738',
    submission_queue_order='pending -> ready -> backend kick -> current -> original completion',
    request_links=dict(next=2408,previous=2416),
    request_fields=dict(rectangles=[17,81],masks=792,dimensions=816,zero_options=[804,808,812,824,828,832,836,840],surfaces=2184),
    real_request_sha256=hashlib.sha256(request).hexdigest(),
    runtime_kernel_sha256=v['kernel_sha256'],
    limitation='Strict sole-ready software-composed BGRA experiment; no GPU producer fences or physical panel qualification',
    presentation_verified=False,desktop_verified=False,device_commands_executed=False)
(DEV/'build/display-analysis-ios16'/a.output).write_text(json.dumps(result,indent=2)+'\n')
print('PASS: original iOS16 queue instructions and real compositor geometry/state match')
