"""Check actual stopped CPU and original-nub publication, without VMM bypass."""
from pathlib import Path
import hashlib, json, re, struct, sys
ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
out=DEV/'build/pmgr-u73'
run=DEV/'build/qemu-early-entry-u73pmgrnative'
verification=json.loads((run/'verification.json').read_text())
kernel=(out/'kernel.prelinked.experimental.macho').read_bytes()
assert hashlib.sha256(kernel).hexdigest()==verification['kernel_sha256']
symbols={name:address for address,names in np.exports(kernel,np.macho(kernel)).items() for name in names}
pc=int(re.search(r'\bPC=([a-fA-F0-9]+)',verification['registers']['return'])[1],16)
assert pc==symbols['_IOFindBSDRoot'],hex(pc)
nub=struct.unpack_from('<Q',(run/'symbol-__ZL13odinPolicyNub.bin').read_bytes())[0]
panic=struct.unpack_from('<Q',(run/'symbol-_debugger_panic_str.bin').read_bytes())[0]
assert 0xfffffff000000000<=nub<0xfffffffffffff000 and not panic
assert not verification['qemu_vmm_present']
report=dict(kernel_sha256=verification['kernel_sha256'],published_original_nub=hex(nub),
    stopped_at='_IOFindBSDRoot',actual_pc=hex(pc),panic_format=panic,
    qemu_vmm_present=False,root_lookup_reached=True,verification=str(run/'verification.json'),
    physical_verified=False,hardware_power_backend=False)
(out/'publication-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
