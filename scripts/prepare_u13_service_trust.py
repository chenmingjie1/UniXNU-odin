"""Audit only newly observed plugin/XPC rejects, then extend local development trust."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
media = dev / 'build/root-media'
image = media / 'system-launch-services-u12.apfs'
run = dev / 'build/qemu-early-entry-u12serviceswrites'
out = media / 'service-dependencies-u13'
out.mkdir(exist_ok=True)
logs = json.loads((run / 'printf.json').read_text())
paths = sorted({r.get('strings', {}).get('0') for r in logs
                if 'rejecting signature' in r.get('format', '')})
assert len(paths) == 6 and all(p and p.startswith('/System/Library/') for p in paths)
command = [sys.executable, '-X', 'utf8', str(dev / 'scripts/inspect_root_exec.py'),
           str(image), '--output-dir', str(out)]
for path in paths:
    command += ['--path', path]
subprocess.run(command, check=True)
new = json.loads((out / 'verification.json').read_text())
assert all(row['code_directories'] and all(not cd['page_hash_mismatches']
           for cd in row['code_directories']) for row in new)
previous = json.loads((media / 'services-development-trust-u12.json').read_text())
wanted = {r['path']: r['sha256'] for r in previous['files']}
baseline = {}
audits = [media / 'dyld-cache-audit-u10.json']
audits += list(media.glob('*/verification.json'))
for audit in audits:
    rows = json.loads(audit.read_text())
    if not isinstance(rows, list):
        continue
    for row in rows:
        if row.get('path') in wanted and row.get('sha256') == wanted[row['path']]:
            assert row['code_directories']
            assert all(not cd['page_hash_mismatches'] for cd in row['code_directories'])
            baseline[row['path']] = row
assert set(baseline) == set(wanted), sorted(set(wanted) - set(baseline))
baseline_path = out / 'baseline-audit.json'
baseline_path.write_text(json.dumps([baseline[k] for k in sorted(baseline)], indent=2) + '\n')
target = media / 'services-development-trust-u13.bundle'
command = [sys.executable, '-X', 'utf8', str(dev / 'scripts/build_development_trust.py'),
           '--audit', str(baseline_path), '--audit', str(out / 'verification.json'),
           '--image', str(image), '--output', str(target)]
result = subprocess.run(command, check=True, capture_output=True, text=True)
(out / 'trust-build.log').write_text(result.stdout + result.stderr, encoding='utf8')
updated = json.loads(target.with_suffix('.json').read_text())
assert set(previous['entries']) < set(updated['entries'])
assert {r['path'] for r in updated['files']} == set(wanted) | set(paths)
receipt = {
    'scope': 'Explicit local owner development trust only; not Apple attestation',
    'evidence_run': str(run.relative_to(root)),
    'new_paths': paths,
    'new_files_verified_without_page_mismatches': True,
    'previous_entries': len(previous['entries']), 'entries': len(updated['entries']),
    'trust_cache_sha256': updated['sha256'],
    'executables_modified': False, 'signature_checks_disabled': False,
    'device_commands_executed': False, 'runtime_verified': False,
}
(out / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
