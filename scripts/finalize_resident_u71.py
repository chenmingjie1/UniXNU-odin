"""Keep the failed physical observation and prepared PC artifact distinct."""
from pathlib import Path
import datetime,json
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
OUT=ROOT/'outputs/MIX4-UniXNU-desktop-u71';manifest=json.loads((OUT/'manifest.json').read_text())
physical=ROOT/'outputs/MIX4-UniXNU-desktop-u70/device-outcome.json'
actual=json.loads(physical.read_text())
actual.update(framebuffer_observation='UniXNU menu plus pre-VM values; no iOS desktop',
    framebuffer_snapshot=str(ROOT/'outputs/MIX4-UniXNU-desktop-u70/resident-snapshots/20261105-231926/framebuffer.png'),
    captured_kernel_stage='0x2f',captured_midr='0x411fd440',
    debug_buffer_initialized=False,physical_desktop_confirmed=False,
    current_control='Resident interface subsequently stopped responding; Windows USB restart did not restore enumeration')
physical.write_text(json.dumps(actual,indent=2)+'\n')
path=DEV/'migration-status.json';status=json.loads(path.read_text())
status.update(updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    phase='u71 PC artifact ready; device recovery required',
    release_manifest=str(OUT/'manifest.json'),image_sha256=manifest['sha256'],
    prepared_candidate=str(OUT/manifest['artifact']),prepared_candidate_device_tested=False,
    native_desktop_boot_candidate=str(OUT/'manifest.json'),
    latest_device_outcome=str(physical),pending_device_outcome=str(OUT/'device-outcome.json'),
    latest_computer_work=str(OUT/'README.md'),current_device_state='Old resident USB no longer responds; Android absent; physical recovery required',
    latest_physical_result='u70 core7 entry and read-only screenshot worked; framebuffer remains UniXNU menu; desktop not reached',
    physical_desktop_verified=False,full_ios_desktop_confirmed=False,
    complete_ios_system=True,native_touch_linked=False,a660_metal_linked=False)
path.write_text(json.dumps(status,indent=2)+'\n')
print('Recorded u70 failed desktop observation and separate u71 prepared artifact')
