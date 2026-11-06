"""Verify every served u67 media range without interpreting USB loss as boot success."""
from pathlib import Path
import datetime, json

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
OUT=ROOT/'outputs/MIX4-UniXNU-desktop-u67'
manifest=json.loads((OUT/'manifest.json').read_text())
runs=sorted((OUT/'runs').iterdir())
accepted=[]
for run in runs:
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    if any(e['event']=='ram_boot_accepted' for e in events):accepted.append((run,events))
run,events=accepted[-1]
reads=[json.loads(line) for line in (run/'reads.jsonl').read_text().splitlines()]
checks=[]
for item in manifest['remote_files']:
    if item['id'] not in (5,6,7,8,9,10):continue
    cursor=0
    for chunk in (r for r in reads if r['file']==item['id']):
        assert chunk['offset']==cursor, chunk
        cursor+=chunk['bytes']
    assert cursor==item['bytes'], (item['uefi_path'],cursor,item['bytes'])
    checks.append(dict(file=Path(item['path']).name,bytes=cursor,sequential_complete=True))
total=sum(r['bytes'] for r in reads)
verification=dict(all_required_media_served=True,partition_writes=False,
    bytes_served=total,read_requests=len(reads),checks=checks)
(run/'complete-media-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
result=dict(device='odin',candidate='u67',run=str(run),
    at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    image_sha256=manifest['sha256'],kernel_sha256=manifest['kernel_sha256'],
    ram_boot_accepted=True,usb_handshake_verified=True,actual_system_and_data_served=True,
    bytes_served=total,read_requests=len(reads),
    exit_boot_services_confirmed=None,xnu_execution_confirmed=None,
    physical_desktop_confirmed=False,physical_screen_observation='awaiting current physical screen',
    partition_writes=False,a660_metal_linked=False,native_touch_linked=False,
    next='Read physical B000/B001 stages and any E000-E005 exception values')
existing=OUT/'device-outcome.json'
if existing.exists():
    old=json.loads(existing.read_text())
    if old.get('run')==str(run):
        for key in ('exit_boot_services_confirmed','xnu_execution_confirmed','physical_screen_observation','screen_evidence'):
            if key in old:result[key]=old[key]
existing.write_text(json.dumps(result,indent=2)+'\n')
path=DEV/'migration-status.json'
status=json.loads(path.read_text())
status.update(native_desktop_boot_candidate='../../outputs/MIX4-UniXNU-desktop-u67/manifest.json',
    latest_physical_result='u67 RAM boot accepted; all System/Data/kernel/trust-cache bytes served; physical screen pending',
    latest_computer_work='../../outputs/MIX4-UniXNU-desktop-u67/README.md',physical_desktop_verified=False)
path.write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(verification,indent=2))
