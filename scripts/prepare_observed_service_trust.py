"""Extend explicit local development trust only for recorded signature rejects."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--evidence-run',required=True)
p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--image',type=Path,required=True)
p.add_argument('--output-tag',required=True)
a=p.parse_args();assert a.evidence_run.isalnum() and a.output_tag.isalnum()
media=DEV/'build/root-media'
out=media/('observed-dependencies-'+a.output_tag)
assert not out.exists(),'Preserve previous audit; use another output tag'
logs=json.loads((DEV/('build/qemu-early-entry-'+a.evidence_run)/'printf.json').read_text())
paths=sorted({row.get('strings',{}).get('0') for row in logs
              if 'rejecting signature' in (row.get('format') or '')})
assert paths and all(path and path.startswith(('/System/Library/',
    '/System/Cryptexes/App/System/Library/', '/Library/Audio/Plug-Ins/HAL/'))
    and '..' not in path.split('/') for path in paths)
previous=json.loads(a.baseline.read_text())
wanted={row['path']:row['sha256'] for row in previous['files']}
assert not set(paths)&set(wanted),'A previously trusted file still fails; investigate instead of adding it again'
baseline={}
for audit in [media/'dyld-cache-audit-u10.json',*media.glob('*/verification.json')]:
    rows=json.loads(audit.read_text())
    if not isinstance(rows,list):continue
    for row in rows:
        if row.get('path') in wanted and row.get('sha256')==wanted[row['path']]:
            assert row['code_directories'] and all(not cd['page_hash_mismatches'] for cd in row['code_directories'])
            baseline[row['path']]=row
assert set(baseline)==set(wanted),sorted(set(wanted)-set(baseline))
out.mkdir()
command=[sys.executable,'-X','utf8',str(DEV/'scripts/inspect_root_exec.py'),
         str(a.image),'--output-dir',str(out)]
for path in paths:command+=['--path',path]
subprocess.run(command,check=True)
new=json.loads((out/'verification.json').read_text())
assert {row['path'] for row in new}==set(paths)
assert all(row['code_directories'] and all(not cd['page_hash_mismatches'] for cd in row['code_directories']) for row in new)
baseline_path=out/'baseline-audit.json'
baseline_path.write_text(json.dumps([baseline[key] for key in sorted(baseline)],indent=2)+'\n')
target=media/('observed-development-trust-'+a.output_tag+'.bundle')
assert not target.exists() and not target.with_suffix('.json').exists()
command=[sys.executable,'-X','utf8',str(DEV/'scripts/build_development_trust.py'),
    '--audit',str(baseline_path),'--audit',str(out/'verification.json'),
    '--image',str(a.image),'--output',str(target)]
r=subprocess.run(command,check=True,capture_output=True,text=True)
(out/'trust-build.log').write_text(r.stdout+r.stderr)
updated=json.loads(target.with_suffix('.json').read_text())
assert set(previous['entries'])<set(updated['entries'])
assert {row['path'] for row in updated['files']}==set(wanted)|set(paths)
record=dict(scope='Computer-only explicit local development trust, not Apple attestation',
    evidence_run=a.evidence_run,baseline=str(a.baseline),new_paths=paths,
    previous_entries=len(previous['entries']),entries=len(updated['entries']),
    added_code_pages=sum(cd['code_slots'] for row in new for cd in row['code_directories']),
    all_page_hashes_verified=True,trust_cache_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    executables_modified=False,signature_checks_disabled=False,device_commands_executed=False,
    runtime_verified=False,desktop_verified=False)
(out/'preparation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
