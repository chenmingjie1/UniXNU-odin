"""Save a bounded source/build snapshot without duplicating large immutable media."""
from pathlib import Path
import datetime,hashlib,json,zipfile
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
OUT=ROOT/'outputs/MIX4-UniXNU-desktop-u71'
stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
archive=OUT/('u71-pc-snapshot-'+stamp+'.zip')
scripts=['build_darwinboot_windows.py','stage_darwinboot_resident.py','build_odin_remote_media.py',
 'build_odin_unixnu_bds.py','assemble_odin_unixnu_firmware.py','check_odin_remote_media.py',
 'check_kernel_readback.py','check_resident_secondary.py','stage_resident_replay.py',
 'qemu_early_entry.py','prepare_resident_desktop_u69.py','prepare_resident_readback_u70.py',
 'package_device_desktop_u64.py','serve_device_desktop_u64.py','snapshot_resident_u70.py',
 'record_resident_u69.py','finalize_resident_u71.py','preserve_resident_u71.py','adt_codec.py']
files=[DEV/'scripts'/name for name in scripts]
files += [DEV/'firmware'/name for name in ('OdinResident.h','OdinResident.c','OdinSecondary.S',
 'OdinRemoteMedia.c','OdinRemoteProtocol.h','OdinKernelReadback.h','OdinDesktopMedia.h')]
for directory in ('darwinboot-u71','remote-media-u71','odin-unixnu-bds-u71','firmware-u71'):
 folder=DEV/'build'/directory
 files += [p for p in folder.iterdir() if p.is_file()]
files += [DEV/'build/device-desktop-u71/manifest.json',
 DEV/'build/device-desktop-u71/esp/EFI/UniXNU/unixnu.toml',
 DEV/'build/device-desktop-u71/esp/EFI/UniXNU/Payloads/kernel.macho',
 DEV/'build/device-desktop-u71/esp/EFI/UniXNU/Payloads/kernel.macho.adt',
 DEV/'build/device-desktop-u71/esp/EFI/UniXNU/Payloads/kernel.macho.trustcache',
 DEV/'build/vm-progress-u68/independent-audit.json',
 DEV/'build/vm-progress-u68/verification.json',DEV/'build/vm-progress-u68/vm-progress.patch',
 DEV/'build/resident-secondary-u69/verification.json',
 DEV/'build/remote-media-u71/check/verification.json',
 DEV/'build/remote-media-u71/readback-check/verification.json',
 DEV/'build/qemu-early-entry-u71core7verified/verification.json',
 ROOT/'outputs/MIX4-UniXNU-desktop-u70/device-outcome.json',
 ROOT/'outputs/MIX4-UniXNU-desktop-u70/resident-snapshots/20261105-231926/framebuffer.png',
 ROOT/'outputs/MIX4-UniXNU-desktop-u70/resident-snapshots/20261105-231926/status.json']
files += [OUT/name for name in ('README.md','manifest.json','SHA256SUMS.txt','device-outcome.json','MIX4-UniXNU-desktop-u71-boot.img')]
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
manifest=json.loads((OUT/'manifest.json').read_text())
assert sha(OUT/manifest['artifact'])==manifest['sha256']
status_path=DEV/'migration-status.json';status=json.loads(status_path.read_text())
status.update(updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 phase='u71 preserved on PC; user unavailable for physical recovery',
 device_operation_policy='User requests preserving PC results only until physical recovery; do not operate or reboot the device',
 current_device_state='Last known: old resident interface unavailable; physical recovery deferred by user',
 prepared_candidate_device_tested=False,physical_desktop_verified=False,full_ios_desktop_confirmed=False)
status_path.write_text(json.dumps(status,indent=2)+'\n');files.append(status_path)
inventory=[]
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
 for path in sorted(set(files)):
  assert path.is_file(),path
  relative=path.relative_to(ROOT).as_posix();z.write(path,relative)
  inventory.append(dict(path=relative,bytes=path.stat().st_size,sha256=sha(path)))
 z.writestr('snapshot-inventory.json',json.dumps(inventory,indent=2)+'\n')
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
media=[dict(path=item['path'],bytes=item['bytes']) for item in manifest['remote_files']
       if item['path'] and item['path'].endswith(('.system','.data'))]
for item in media:assert Path(item['path']).stat().st_size==item['bytes']
record=dict(snapshot=str(archive),sha256=sha(archive),files=len(inventory),
 large_media_preserved_in_place=media,phone_operated=False,desktop_fixed=False,
 next='After user confirms Android recovery, load u71 using serve_device_desktop_u64.py --release u71 --boot; observe with snapshot_resident_u70.py --release u71')
(OUT/'preservation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
