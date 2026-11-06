#!/usr/bin/env python3
"""Apply the pinned iOS 16.5 series to the separate archive import."""
from pathlib import Path
import hashlib, json, shutil, subprocess
ROOT = Path('/home/odin/unixnu-odin-build')
REF = ROOT / 'xnu-reference'
TREE = ROOT / 'upstream/.cache/xnu-work'
OUT = ROOT / 'evidence'
OUT.mkdir(exist_ok=True)
if TREE.exists():
    raise SystemExit('Fresh output required; existing patched tree was preserved')
shutil.copytree(REF, TREE)
patchdir = ROOT / 'device/patches/xnu'
report = []
for line in (patchdir/'series').read_text().splitlines():
    name = line.strip()
    if not name or name.startswith('#'): continue
    patch = patchdir/name
    check = subprocess.run(['git','apply','--check',str(patch)],cwd=TREE,capture_output=True,text=True)
    entry = {'name':name, 'sha256':hashlib.sha256(patch.read_bytes()).hexdigest(), 'check':check.returncode, 'diagnostic':check.stderr}
    if check.returncode == 0:
        apply = subprocess.run(['git','apply',str(patch)],cwd=TREE,capture_output=True,text=True)
        entry['apply'] = apply.returncode
        entry['diagnostic'] += apply.stderr
    report.append(entry)
    (OUT/'patch-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(name,entry.get('apply',check.returncode),flush=True)
    if check.returncode or entry.get('apply'):
        raise SystemExit('Ordered patch series stopped: '+name+'\n'+entry['diagnostic'])
print('All',len(report),'patches applied to archive import (no fabricated Git HEAD)',flush=True)
