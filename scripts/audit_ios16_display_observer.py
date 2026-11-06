"""Qualify read-only display-client entry/return observation points in iOS16."""
from pathlib import Path
import argparse,hashlib,json,struct,sys

ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build-tag',required=True)
a=p.parse_args();assert a.build_tag.isalnum()
build=DEV/('build/display-owner-'+a.build_tag)
source=(DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
candidate=(build/'kernel.prelinked.experimental.macho').read_bytes()
discovery=json.loads((DEV/'build/display-analysis-ios16/dispatch-discovery.json').read_text())
assert hashlib.sha256(source).hexdigest()==discovery['candidate_sha256']
original=np.macho(source);linked=np.macho(candidate)
def read(blob,image,at,size):
    start=np.backed_offset(image['segments'],at,size,len(blob))
    return blob[start:start+size]

entry=0xfffffff004c012a0;returned=0xfffffff004c014a0
client=next(c for c in discovery['dispatch_candidates'] if c['entries']==187)
assert next(m for m in client['methods'] if m['slot']==168)['address']==hex(entry)
assert struct.unpack('<Q',read(source,original,int(client['vptr'],16)+168*8,8))[0]==entry
method=read(source,original,entry,0x20c)
assert read(candidate,linked,entry,len(method))==method
words={entry+i:struct.unpack_from('<I',method,i)[0] for i in range(0,len(method),4)}
assert words[entry]==0xd10203ff  # sub sp, sp, #128
assert words[entry+8]==0x9101c3fd  # add x29, sp, #112
assert words[0xfffffff004c012bc]==0xb81ec3a1  # stur w1, [x29,#-20]
assert words[0xfffffff004c012f0]==0xb85ec3a8  # ldur w8, [x29,#-20]
assert words[0xfffffff004c012f4]==0x71015d08  # subs w8, w8, #87
assert words[returned-4]==0xb85fc3a0  # ldur w0, [x29,#-4]
assert words[returned]==0xa9477bfd  # restored FP/LR follows status load
assert words[returned+4]==0x910203ff and words[returned+8]==0xd65f03c0
record=dict(passed=True,target='iOS16.5/20F66',
    candidate_sha256=hashlib.sha256(candidate).hexdigest(),
    original_method_sha256=hashlib.sha256(method).hexdigest(),
    entry=hex(entry),returned=hex(returned),
    entry_registers=dict(X00='client',X01='selector',X02='IOExternalMethodArguments pointer'),
    return_registers=dict(X00='IOReturn low 32 bits'),
    return_sp_offset_from_entry=-128,
    note='Entry/return records are observations, not proof of rendering or successful swap',
    method_bytes_modified=False,device_commands_executed=False)
(build/'display-observer-contract.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
