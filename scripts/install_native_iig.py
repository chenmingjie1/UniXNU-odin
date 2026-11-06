"""Linux: install audited real IIG sources into the isolated UniXNU build only."""
from pathlib import Path
import hashlib
import json
import shutil
import tarfile
import sys

ROOT = Path('/home/odin/unixnu-odin-build')
STAGE = ROOT / 'iig-tools/native8796'
SRC = ROOT / 'upstream/.cache/xnu-work'
OBJ = ROOT / 'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT'
report = json.loads((STAGE/'verification.json').read_text())
assert len(report['results']) == 17
assert all(r['compile_returncode'] == 0 for r in report['results'])
backup = STAGE/'before-real-iig.tar.gz'
if backup.exists() and '--resume' not in sys.argv:
    raise SystemExit('Already installed or backup exists; inspect instead of reinstalling')
paths = list((OBJ/'DriverKit').glob('*.iig.cpp'))
paths += list((OBJ/'DriverKit').glob('*.h'))
for row in report['results']:
    paths.append(OBJ/(row['name']+'.iig.cpo'))
for base in (SRC/'iokit', ROOT/'upstream/build/xnu/ios-obj'):
    paths.extend(base.rglob('IORPC.h'))
if not backup.exists():
    with tarfile.open(backup, 'w:gz') as t:
        for p in sorted(set(paths)):
            if p.is_file():
                t.add(p, arcname=str(p.relative_to(ROOT)), recursive=False)
legacy_headers = STAGE/'legacy-headers'
legacy_headers.mkdir(exist_ok=True)
for row in report['results']:
    name = row['name']
    assert hashlib.sha256((SRC/'iokit/DriverKit'/(name+'.iig')).read_bytes()).hexdigest() == row['input_iig_sha256']
    if not (legacy_headers/(name+'.h')).exists():
        shutil.copyfile(OBJ/'DriverKit'/(name+'.h'), legacy_headers/(name+'.h'))
    for suffix in ('.iig.cpp',):
        shutil.copyfile(STAGE/'generated'/(name+suffix), OBJ/'DriverKit'/(name+suffix))
    # Recompile with the same headers all other kernel objects will now see.
    # Do not silently install an object built with private header overrides.

restored = []
for p in sorted(set(paths)):
    if p.name == 'IORPC.h' and p.is_file():
        relative = 'DriverKit' if '/DriverKit/' in str(p) else 'IOKit'
        original = ROOT/'xnu-reference/iokit'/relative/'IORPC.h'
        p.chmod(p.stat().st_mode | 0o200)
        shutil.copyfile(original, p)
        restored.append(str(p.relative_to(ROOT)))
wrapper = ROOT/'iig-tools/iig-8796-cached'
wrapper.write_text('''#!/usr/bin/env python3
from pathlib import Path
import sys,json,hashlib,shutil
root=Path('/home/odin/unixnu-odin-build/iig-tools/native8796')
args=sys.argv[1:]
def value(k): return args[args.index(k)+1]
source=Path(value('--def')); name=source.stem
rows=json.loads((root/'verification.json').read_text())['results']
row=next(r for r in rows if r['name']==name)
assert hashlib.sha256(source.read_bytes()).hexdigest()==row['input_iig_sha256'], 'Changed IIG input; regenerate and audit first'
cpp=root/'generated'/(name+'.iig.cpp')
assert hashlib.sha256(cpp.read_bytes()).hexdigest()==row['adapted_source_sha256']
shutil.copyfile(root/'legacy-headers'/(name+'.h'),value('--header'))
shutil.copyfile(cpp,value('--impl'))
''')
wrapper.chmod(0o755)
(STAGE/'installation.json').write_text(json.dumps({
    'backup': str(backup), 'restored_iorpc_headers': restored,
    'real_iig_sources_installed': 17, 'kernel_linked': False, 'device_tested': False}, indent=2)+'\n')
print('Installed 17 real IIG sources; restored',len(restored),'original IORPC headers; existing kernels backed up')
