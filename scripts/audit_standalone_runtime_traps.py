"""Match captured standalone instruction runs to the audited original root.

Only an actual unique code match yields a process-specific ASLR slide.
Uncaptured or ambiguous traps remain unresolved; no runtime changes occur.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from inspect_root_exec import apfs

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--analysis',type=Path,required=True)
p.add_argument('--audit',type=Path,required=True)
p.add_argument('--image',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
assert not a.output.exists()
d=json.loads(a.analysis.read_text())
traps=[r for r in d['observed_el0_breakpoints'] if not r['unique_original_match'] and r.get('matched_instructions')]
c=apfs.Container(a.image);v=apfs.pick_volume(c,None)
hits={r['runtime_pc']:[] for r in traps}
for entry in json.loads(a.audit.read_text()):
    data=v.inode(v.lookup(entry['path'])[0]).contents()
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    for trap in traps:
        needle=bytes.fromhex(trap['matched_instructions'])
        offset=data.find(needle)
        while offset>=0:
            for part in entry.get('slices',[dict(offset=0,bytes=len(data))]):
                start=part['offset'];end=start+part['bytes']
                if not start<=offset<end:continue
                at=start+32
                for _ in range(struct.unpack_from('<I',data,start+16)[0]):
                    cmd,size=struct.unpack_from('<II',data,at)
                    if cmd==25:
                        _,va,_,fo,fs=struct.unpack_from('<16s4Q',data,at+8)
                        if fo<=offset-start and offset-start+len(needle)<=fo+fs:
                            pc=va+offset-start-fo+len(needle)-4
                            slide=int(trap['runtime_pc'],16)-pc
                            assert slide>=0 and slide%4096==0
                            hits[trap['runtime_pc']].append(dict(path=entry['path'],
                                sha256=entry['sha256'],original_pc=hex(pc),slide=hex(slide),
                                file_offset=offset,slice_offset=start,matched_bytes=len(needle)))
                    at+=size
            offset=data.find(needle,offset+1)
c.close()
record=dict(source_analysis=str(a.analysis),source_audit=str(a.audit),
    matched_traps=[dict(runtime_pc=r['runtime_pc'],matches=hits[r['runtime_pc']],
                        unique_original_match=len(hits[r['runtime_pc']])==1) for r in traps],
    other_traps_left_unresolved=True,executables_modified=False,device_commands_executed=False)
a.output.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
