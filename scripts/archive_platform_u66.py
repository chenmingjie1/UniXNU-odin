"""Keep reproducible u66 inputs and qualified CPU replay evidence together."""
from pathlib import Path
import hashlib, json, shutil, struct

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
OUT=ROOT/'outputs/MIX4-UniXNU-desktop-u66'
BUILD=DEV/'build/platform-u66'
manifest=json.loads((OUT/'manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BUILD/'kernel.prelinked.experimental.macho')==manifest['kernel_sha256']
checks=[]
for tag in ('u66physicaldtirq','u66fullmediairq','u66exceptionnative'):
    folder=DEV/('build/qemu-early-entry-'+tag)
    data=json.loads((folder/'verification.json').read_text())
    assert data['kernel_sha256']==manifest['kernel_sha256']
    stage=struct.unpack('<Q',(folder/'symbol-_odin_platform_last_stage.bin').read_bytes()[:8])[0]
    if tag=='u66exceptionnative':
        assert data['early_exception_handler_reached'] and stage==0x23
    else:
        assert data['halted_before_symbol']=='_pe_arm_init_interrupts' and stage==0x2f
    target=OUT/'checks'/tag
    target.mkdir(parents=True,exist_ok=True)
    for name in ('verification.json','command.json','symbol-_odin_platform_last_stage.bin'):
        shutil.copy2(folder/name,target/name)
    checks.append(dict(tag=tag,last_stage=hex(stage),kind='computer CPU replay',phone_qualified=False))
for name in ('verification.json','platform-progress.patch','kernel-link.log','kernel-crypto-seal.log',
             'link_kernel.sh','independent-audit.json','prelink-attempt.json'):
    shutil.copy2(BUILD/name,OUT/name)
source=OUT/'source'
source.mkdir(exist_ok=True)
for name in ('install_platform_progress_u66.py','record_u65_screen.py',
             'prepare_platform_desktop_u66.py','serve_device_desktop_u64.py',
             'qemu_early_entry.py','archive_platform_u66.py'):
    shutil.copy2(DEV/'scripts'/name,source/name)
(OUT/'checks/summary.json').write_text(json.dumps(checks,indent=2)+'\n')
(OUT/'README.md').write_text('''# MIX 4 UniXNU u66

This candidate keeps the u65 firmware byte for byte and serves a different,
source-built kernel over the read-only USB file protocol. Its Android boot
image SHA therefore equals u65; the separately pinned USB kernel SHA differs.
The firmware stores file names and sizes. All staged names and sizes were
verified unchanged. Historical u62/u65 payloads were not overwritten.

The kernel continues normal boot after each early-platform checkpoint. B000
shows the last stage and B001 its return address. Unexpected exceptions before
arm_vm_init show E000-5 (ESR, ELR, FAR, SCTLR, SPSR, TCR) using KVA vectors.
Normal vectors are restored before VM takeover. No low-framebuffer diagnostic
stores are added after that point. A normal path has no added diagnostic halt.

Computer checks exercised the compiled kernel with the physical device tree,
full System/Data/trust-cache inputs, and a deliberate early-C BRK. The normal
replay reaches the GIC entry and stage 2F; the fault executes the KVA handler.
These checks emulate the CPU, not SM8350 peripherals or an actual desktop.
An initial stripped fixture left TrustCache at PA zero and panicked in
phystokv. Filling the media descriptors as DarwinBoot does resolves that
fixture error. It is not evidence of a phone-side TrustCache bug.

The u65 phone photo proves XNU C entry before PE_init_platform; it does not
prove PE itself hung. u66 exists to resolve the unobserved interval.
GPU Metal and native physical touch remain unlinked in this UniXNU build.
No flash/erase/slot switching or Android partition writes are implemented.

RAM boot and media server (from the workspace root):
```
python work/UniXNU-odin/scripts/serve_device_desktop_u64.py --release u66 --boot --seconds 1800
```
''')
files=[dict(path=str(p.relative_to(OUT)),bytes=p.stat().st_size,sha256=sha(p))
       for p in sorted(OUT.rglob('*')) if p.is_file() and 'runs' not in p.relative_to(OUT).parts
       and p.name!='archive-manifest.json']
(OUT/'archive-manifest.json').write_text(json.dumps(dict(files=files,device_qualification=False),indent=2)+'\n')
print('u66 source, source-link receipt, CPU checks and limitations archived')
