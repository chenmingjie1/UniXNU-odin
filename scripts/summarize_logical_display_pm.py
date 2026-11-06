"""Report actual logical-PM callbacks and original submission from host evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

DEV=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',required=True)
p.add_argument('--build-tag',required=True)
a=p.parse_args()
assert a.tag.isalnum() and a.build_tag.isalnum()
run=DEV/('build/qemu-early-entry-'+a.tag)
build=DEV/('build/display-owner-'+a.build_tag)
v=json.loads((run/'verification.json').read_text())
kernel_sha=hashlib.sha256((build/'kernel.prelinked.experimental.macho').read_bytes()).hexdigest()
assert v['kernel_sha256']==kernel_sha
logs=json.loads((run/'printf.json').read_text())
pm=[dict(format=r['format'],arguments=r['slots'][:6],caller=r.get('caller'))
    for r in logs if 'OdinLegacyGOPDisplay: logical PM' in (r['format'] or '')]
callbacks=[r for r in pm if ' callback ' in r['format']]
ready=[r for r in callbacks if r['arguments'][0]==1 and r['arguments'][2]==1 and r['arguments'][4]==0]
trace=(run/'trace.log').read_text()
addresses={'bypass':'0xfffffff004c17c6c','submit_block':'0xfffffff004c17c98',
           'original_validation_call':'0xfffffff004c185b8'}
executed={name:bool(re.search(re.escape(addr)+r':',trace)) for name,addr in addresses.items()}
counts_path=run/'symbol-_odin_surface_inspections.bin'
counts=list(struct.unpack('<'+'I'*(counts_path.stat().st_size//4),counts_path.read_bytes())) if counts_path.exists() else []
result=dict(scope='Computer replay, no device commands',kernel_sha256=kernel_sha,
    pm_logs=pm,logical_scheduling_callback_verified=bool(ready),
    executed_original_blocks=executed,surface_counters=counts,
    original_submission_reached=bool(executed['original_validation_call'] and counts and counts[0]),
    presentation_implemented=False,desktop_verified=False,device_commands_executed=False)
(run/'logical-pm-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
