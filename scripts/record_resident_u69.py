"""Record transport/secondary-entry evidence separately from desktop success."""
from pathlib import Path
import argparse,datetime,json
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--release',choices=['u69','u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82'],default='u69');parser.add_argument('--screen-state');options=parser.parse_args()
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
OUT=ROOT/('outputs/MIX4-UniXNU-desktop-'+options.release)
manifest=json.loads((OUT/'manifest.json').read_text())
accepted=[]
for run in sorted((OUT/'runs').iterdir()):
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    if any(e['event']=='ram_boot_accepted' for e in events):accepted.append((run,events))
run,events=accepted[-1]
reads=[json.loads(line) for line in (run/'reads.jsonl').read_text().splitlines()]
checks=[]
for item in manifest['remote_files']:
    if item['id'] not in (5,6,7,8,9,10):continue
    cursor=0
    for chunk in (r for r in reads if r['file']==item['id']):
        assert chunk['offset']==cursor
        cursor+=chunk['bytes']
    checks.append(dict(file=Path(item['path']).name,bytes=cursor,expected_bytes=item['bytes'],complete=cursor==item['bytes']))
complete=all(row['complete'] for row in checks)
resident=next((e for e in events if e['event']=='resident_core7_control_available'),None)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
result=dict(at=now,run=str(run),candidate=options.release,ram_boot_accepted=True,
    kernel_sha256=manifest['kernel_sha256'],image_sha256=manifest['sha256'],
    all_required_media_served=complete,checks=checks,
    bytes_served=sum(r['bytes'] for r in reads),read_requests=len(reads),
    resident_usb_control_confirmed=resident is not None,
    secondary_entry_confirmed=bool(resident and 'entered=1:' in resident['status']),
    secondary_status=resident['status'] if resident else None,
    exit_boot_services=False,physical_desktop_confirmed=False,
    native_touch_linked=manifest.get('native_touch_linked',False),a660_metal_linked=False,partition_writes=False)
path=OUT/'device-outcome.json'
if path.exists():
    prior=json.loads(path.read_text())
    if prior.get('run')==str(run):
        for key in ('physical_desktop_confirmed','physical_screen_observation','screen_evidence'):
            if key in prior:result[key]=prior[key]
path.write_text(json.dumps(result,indent=2)+'\n')
if options.screen_state:
 result['physical_screen_observation']=options.screen_state
 path.write_text(json.dumps(result,indent=2)+'\n')
if complete:(run/'complete-media-verification.json').write_text(json.dumps(result,indent=2)+'\n')
status_path=DEV/'migration-status.json';status=json.loads(status_path.read_text())
status.update(updated_at=now,phase=options.release+' HakiOS-derived resident handoff physical attempt',
    release_manifest=str(OUT/'manifest.json'),image_sha256=manifest['sha256'],
    prepared_candidate=str(OUT/manifest['artifact']),prepared_candidate_device_tested=True,
    native_desktop_boot_candidate=str(OUT/'manifest.json'),
    latest_device_outcome=str(path),latest_computer_work=str(OUT/'README.md'),
    physical_desktop_verified=result['physical_desktop_confirmed'],
    current_device_state=options.release+' RAM boot accepted; resident USB available' if resident else options.release+' RAM boot accepted; see device outcome for media/handoff status',
    latest_physical_result=options.release+' actual observations only; desktop remains unconfirmed',
    complete_ios_system=True,device_commands=True,full_ios_desktop_confirmed=result['physical_desktop_confirmed'])
status_path.write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(result,indent=2))
