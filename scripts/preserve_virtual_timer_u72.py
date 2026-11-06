"""Preserve the u72 compatibility fix and u71 physical evidence; no device I/O."""
from pathlib import Path
import datetime, hashlib, json, zipfile

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = ROOT/'outputs/MIX4-UniXNU-desktop-u72'
stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
archive = OUT/('u72-pc-snapshot-'+stamp+'.zip')
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8<<20), b''): h.update(block)
    return h.hexdigest()

manifest = json.loads((OUT/'manifest.json').read_text())
assert sha(OUT/manifest['artifact']) == manifest['sha256']
assert sha(DEV/'build/virtual-timer-u72/kernel.prelinked.experimental.macho') == manifest['kernel_sha256']
files = [p for p in OUT.iterdir() if p.is_file() and p.suffix != '.zip' and p.name != 'preservation.json']
scripts = ['preserve_virtual_timer_u72.py','install_virtual_timer_u72.py','finalize_virtual_timer_u72.py',
    'build_darwinboot_windows.py','stage_darwinboot_resident.py','build_odin_remote_media.py',
    'build_odin_unixnu_bds.py','assemble_odin_unixnu_firmware.py','check_odin_remote_media.py',
    'check_kernel_readback.py','check_resident_secondary.py','stage_resident_replay.py',
    'qemu_early_entry.py','prepare_resident_readback_u70.py','prepare_ios16_prelink.py',
    'audit_ios16_prelink.py','apply_original_driver_policy.py','package_device_desktop_u64.py',
    'serve_device_desktop_u64.py','snapshot_resident_u70.py','record_resident_u69.py','adt_codec.py']
files += [DEV/'scripts'/name for name in scripts]
files += list((DEV/'firmware').glob('Odin*'))
files += [DEV/'configs/original-driver-policy.toml']
for name in ['darwinboot-u72','remote-media-u72','odin-unixnu-bds-u72','firmware-u72','virtual-timer-u72']:
    files += [p for p in (DEV/'build'/name).iterdir() if p.is_file()]
for name in ['remote-media-u72/check','remote-media-u72/readback-check','qemu-early-entry-u72core7verified']:
    files += [p for p in (DEV/'build'/name).iterdir()
              if p.is_file() and p.suffix in ('.json','.txt','.log')]
stage = DEV/'build/device-desktop-u72'
files += [stage/'manifest.json', stage/'esp/EFI/UniXNU/unixnu.toml']
files += [p for p in (stage/'esp/EFI/UniXNU/Payloads').iterdir()
          if p.name in ('kernel.macho.adt','kernel.macho.trustcache')]
previous = ROOT/'outputs/MIX4-UniXNU-desktop-u71'
files += [previous/'device-outcome.json',previous/'manifest.json']
files += [p for p in (previous/'resident-snapshots/20261106-022309').iterdir()
          if p.is_file() and p.name != 'framebuffer.bin']
files += [p for p in (previous/'runs/20261106-021742').iterdir()
          if p.is_file() and p.suffix in ('.json','.jsonl')]
files += [ROOT/'work/hakios-upstream/xnu/hakios.patch',
    ROOT/'work/UniXNU-components/Reference-haydn-iamojz-9710ddf99b1d23b54b93cd683f6af1e37a43c87b/patches/xnu/0001-sm8350-el1pcen-physical-timer.patch']

media = [dict(path=item['path'],bytes=item['bytes']) for item in manifest['remote_files']
         if item['path'] and item['path'].endswith(('.system','.data'))]
for item in media: assert Path(item['path']).stat().st_size == item['bytes']
status_path = DEV/'migration-status.json'
status = json.loads(status_path.read_text())
status.update(updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    phase='u72 preserved on PC; user unavailable for physical recovery',
    device_operation_policy='Preserve PC results only until user confirms Android recovery; no device queries, reboot or launch',
    current_device_state='Last observed u71 undefined-instruction panic; physical recovery deferred by user',
    prepared_candidate_device_tested=False,device_commands=False,
    physical_desktop_verified=False,full_ios_desktop_confirmed=False,
    latest_preservation_archive=str(archive))
status_path.write_text(json.dumps(status,indent=2)+'\n')
files.append(status_path)
inventory=[]
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for path in sorted(set(files)):
        assert path.is_file(),path
        relative=path.relative_to(ROOT).as_posix()
        z.write(path,relative)
        inventory.append(dict(path=relative,bytes=path.stat().st_size,sha256=sha(path)))
    z.writestr('snapshot-inventory.json',json.dumps(inventory,indent=2)+'\n')
with zipfile.ZipFile(archive) as z: assert z.testzip() is None
record=dict(snapshot=str(archive),sha256=sha(archive),files=len(inventory),
    large_media_preserved_in_place=media,phone_operated=False,
    candidate_device_tested=False,desktop_fixed=False,
    next='After confirmed Android recovery: serve_device_desktop_u64.py --release u72 --boot, then snapshot_resident_u70.py --release u72 with matching --wait-run')
(OUT/'preservation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
