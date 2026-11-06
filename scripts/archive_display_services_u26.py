"""Preserve computer-only service/dispatch runs without rewriting u25 evidence."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,tarfile

ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run',action='append',required=True)
p.add_argument('--output-tag',required=True)
a=p.parse_args();assert a.output_tag.isalnum() and all(t.isalnum() for t in a.run)
OUT=ROOT/('outputs/MIX4-UniXNU-display-'+a.output_tag)
assert not OUT.exists(),'Preserve previous evidence; use a new output tag'
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
analyses=[]
for tag in a.run:
    folder=DEV/('build/qemu-early-entry-'+tag)
    row=json.loads((folder/'desktop-runtime-analysis.json').read_text())
    assert not row['device_commands_executed']
    analyses.append(dict(tag=tag,analysis=row))
OUT.mkdir()
for tag in a.run:
    folder=DEV/('build/qemu-early-entry-'+tag);target=OUT/'runtime'/tag;target.mkdir(parents=True)
    for name in ('verification.json','desktop-runtime-analysis.json','framebuffer.png',
                 'printf.json','userspace-live.log','register-observations.json','command.json','panic.json'):
        source=folder/name
        if source.exists():shutil.copy2(source,target/name)
sources=[DEV/'scripts'/name for name in ('qemu_early_entry.py','run_u15_host_display.ps1',
    'analyze_host_desktop_runtime.py','audit_ios16_display_observer.py',
    'prepare_launch_services_root.py','prepare_chrono_trust_u26.py','archive_display_services_u26.py')]
sources+=list((DEV/'build/root-media/chrono-audit-u26').glob('*.json'))
sources+=[DEV/'build/root-media/system-chrono-services-u26.json',
          DEV/'build/display-owner-u25/display-observer-contract.json']
archive=OUT/'service-and-observer-source.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for source in sources:
        if source.is_file():tar.add(source,arcname=source.relative_to(ROOT))
media=json.loads((DEV/'build/root-media/system-chrono-services-u26.json').read_text())
trust=json.loads((DEV/'build/root-media/chrono-audit-u26/preparation.json').read_text())
record=dict(updated_at=datetime.now(timezone.utc).isoformat(),
    scope='Computer-only original iOS16.5 service/dispatch analysis; not a phone image',
    root_sha256=media['sha256'],root_bytes=media['bytes'],
    existing_file_payloads_preserved=media['existing_file_payloads_preserved'],
    trust_cache_sha256=trust['trust_cache_sha256'],
    desktop_verified=False,presentation_implemented=False,device_commands_executed=False,
    runs=analyses,source_archive=dict(file=archive.name,sha256=digest(archive)))
(OUT/'progress.json').write_text(json.dumps(record,indent=2)+'\n')
status_path=DEV/'migration-status.json';status=json.loads(status_path.read_text())
status.update(updated_at=record['updated_at'],
    phase='Host-only '+a.output_tag+': original Chrono service and display-client dispatch verification; no desktop',
    host_evidence=str((OUT/'progress.json').relative_to(ROOT)).replace('\\','/'),
    host_full_system_root_bytes=record['root_bytes'],host_new_boot_image_created=False,
    latest_host_candidate_device_tested=False)
status['display_services_'+a.output_tag]=dict(evidence=status['host_evidence'],
    root_sha256=record['root_sha256'],trust_cache_sha256=record['trust_cache_sha256'],
    runs=a.run,desktop_verified=False,device_commands_executed=False)
status_path.write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
manifest={str(path.relative_to(OUT)):digest(path) for path in OUT.rglob('*') if path.is_file()}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(output=str(OUT),files=len(manifest),desktop_verified=False),indent=2))
