"""Add only the two audited original Chrono services to local development trust."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
media=DEV/'build/root-media';out=media/'chrono-audit-u26'
previous=json.loads((media/'services-cryptex-trust-u13.json').read_text())
wanted={r['path']:r['sha256'] for r in previous['files']}
baseline={}
for audit in [media/'dyld-cache-audit-u10.json',*media.glob('*/verification.json')]:
    rows=json.loads(audit.read_text())
    if not isinstance(rows,list):continue
    for row in rows:
        if row.get('path') in wanted and row.get('sha256')==wanted[row['path']]:
            assert row['code_directories'] and all(not cd['page_hash_mismatches'] for cd in row['code_directories'])
            baseline[row['path']]=row
assert set(baseline)==set(wanted),sorted(set(wanted)-set(baseline))
added=json.loads((out/'verification.json').read_text())
assert len(added)==2 and all(r['code_directories'] and all(not cd['page_hash_mismatches'] for cd in r['code_directories']) for r in added)
baseline_path=out/'baseline-audit.json'
baseline_path.write_text(json.dumps([baseline[k] for k in sorted(baseline)],indent=2)+'\n')
target=media/'chrono-development-trust-u26.bundle'
command=[sys.executable,'-X','utf8',str(DEV/'scripts/build_development_trust.py'),
    '--audit',str(baseline_path),'--audit',str(out/'verification.json'),
    '--image',str(media/'system-chrono-services-u26.apfs'),'--output',str(target)]
r=subprocess.run(command,check=True,capture_output=True,text=True)
(out/'trust-build.log').write_text(r.stdout+r.stderr)
updated=json.loads(target.with_suffix('.json').read_text())
assert set(previous['entries'])<=set(updated['entries'])
assert {r['path'] for r in updated['files']}==set(wanted)|{r['path'] for r in added}
record=dict(scope='Computer-only local owner development trust, not Apple attestation',
    source='services-cryptex-trust-u13.bundle',new_jobs=['com.apple.chronod','com.apple.liveactivitiesd'],
    previous_entries=len(previous['entries']),entries=len(updated['entries']),
    added_code_pages=sum(cd['code_slots'] for row in added for cd in row['code_directories']),
    all_page_hashes_verified=True,trust_cache_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    executables_modified=False,signature_checks_disabled=False,device_commands_executed=False,
    runtime_verified=False,desktop_verified=False)
(out/'preparation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
