"""Archive the exact u65 candidate, tests, and u64 physical result."""
from pathlib import Path
import hashlib
import json
import shutil

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = ROOT / 'outputs/MIX4-UniXNU-desktop-u65'
manifest = json.loads((OUT / 'manifest.json').read_text())
assert hashlib.sha256((OUT / manifest['artifact']).read_bytes()).hexdigest() == manifest['sha256']
inputs = [
    'firmware/OdinRemoteMedia.c', 'firmware/OdinRemoteProtocol.h',
    'scripts/build_odin_remote_media.py', 'scripts/check_odin_remote_media.py',
    'scripts/build_odin_unixnu_bds.py', 'scripts/OdinUniXNUHandoff.c',
    'scripts/assemble_odin_unixnu_firmware.py', 'scripts/package_device_desktop_u64.py',
    'scripts/serve_device_desktop_u64.py', 'scripts/archive_device_desktop_u65.py',
    'build/remote-media-u64/verification.json', 'build/remote-media-u64/OdinRemoteFiles.h',
    'build/remote-media-u64/check/verification.json', 'build/remote-media-u64/check/check.c',
    'build/odin-unixnu-bds-u65/verification.json', 'build/odin-unixnu-bds-u65/OdinUniXNU.c',
    'build/odin-unixnu-bds-u65/build.log', 'build/firmware-u65/verification.json',
    'build/firmware-u65/build.log', 'build/device-desktop-u63/manifest.json',
]
archived = []
for name in inputs:
    src = DEV / name
    dst = OUT / 'evidence' / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    archived.append({'path': str(dst.relative_to(OUT)), 'sha256': hashlib.sha256(dst.read_bytes()).hexdigest()})
old = ROOT / 'outputs/MIX4-UniXNU-desktop-u64/runs/20261104-212509'
for name in ('result.json', 'events.jsonl'):
    shutil.copy2(old / name, OUT / ('u64-' + name))
report = {
    'candidate': 'u65', 'image_sha256': manifest['sha256'],
    'state': 'Built and checked; waiting for physical recovery of u64',
    'physical_desktop_confirmed': False, 'partition_writes': False,
    'u64_ram_boot_accepted': True, 'u64_bytes_served': 0,
    'u64_user_observation': 'UniXNU menu or error text; exact text not yet supplied',
    'usb_hardware_qualified': False,
    'changes': ['BDS installs filesystem and explicitly pumps USB before UniXNU starts',
                'Wait for vendor Connected event before submitting a USB transfer',
                'Bounded timeout and disconnect cancellation'],
    'checks': manifest['checks'], 'evidence': archived,
    'a660_metal_linked': False, 'native_touch_linked': False,
}
runs = sorted((OUT / 'runs').glob('*')) if (OUT / 'runs').exists() else []
if runs:
    latest = runs[-1]
    events_path = latest / 'events.jsonl'
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    accepted = next((e for e in events if e['event'] == 'ram_boot_accepted'), None)
    if accepted:
        report.update(state='Physical RAM boot accepted; inspect runtime result and screen separately',
                      latest_device_run=str(latest), device_ram_boot_accepted=True)
        reads_path = latest / 'reads.jsonl'
        reads = [json.loads(line) for line in reads_path.read_text().splitlines()] if reads_path.exists() else []
        report['device_bytes_served_at_archive'] = sum(r['bytes'] for r in reads)
        report['device_usb_media_reads_observed'] = bool(reads)
        result_path = latest / 'result.json'
        if result_path.exists():
            report['latest_device_transport_result'] = json.loads(result_path.read_text())
    report['changes'].append('Retain pre-ExitBootServices loader failures on USB and allow Android reboot; no post-EBS recovery claim')
(OUT / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
status_path = DEV / 'migration-status.json'
status = json.loads(status_path.read_text())
status.update(native_desktop_boot_image_created=True,
              native_desktop_boot_candidate='../../outputs/MIX4-UniXNU-desktop-u65/manifest.json',
              physical_desktop_verified=False,
              latest_physical_result='u64 RAM boot accepted; zero media reads; USB unavailable',
              latest_computer_work='../../outputs/MIX4-UniXNU-desktop-u65/progress.json')
if report.get('device_ram_boot_accepted'):
    status['latest_physical_result'] = 'u65 RAM boot accepted; USB media reads observed; physical desktop not yet confirmed'
outcome_path = OUT / 'device-outcome.json'
if outcome_path.exists():
    outcome = json.loads(outcome_path.read_text())
    if outcome.get('image_sha256') == manifest['sha256'] and outcome.get('actual_system_and_data_served'):
        status['latest_physical_result'] = 'u65 USB media transfer complete; physical kernel/desktop awaiting screen evidence'
status_path.write_text(json.dumps(status, indent=2) + '\n')
print(json.dumps({k: report[k] for k in ('state', 'image_sha256', 'physical_desktop_confirmed')}, indent=2))
