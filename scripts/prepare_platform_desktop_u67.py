"""Pin u67 USB payloads, reusing the verified u65 firmware and exact file sizes.

Only the served kernel changes. Firmware stores paths and sizes, not payload
hashes, so equal-sized payload replacement does not require another FV build.
The old stage and all historical manifests remain unchanged.
"""
from pathlib import Path
import copy, hashlib, json, shutil

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
OLD=DEV/'build/device-desktop-u63'
NEW=DEV/'build/device-desktop-u67'
OUT=ROOT/'outputs/MIX4-UniXNU-desktop-u67'
NEW.mkdir(exist_ok=False)
OUT.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=DEV/'build/platform-u67'
audit=json.loads((build/'independent-audit.json').read_text())
assert audit['passed']
prior=json.loads((ROOT/'outputs/MIX4-UniXNU-desktop-u65/manifest.json').read_text())
media=copy.deepcopy(json.loads((OLD/'manifest.json').read_text()))
for source in sorted((OLD/'esp').rglob('*')):
    if not source.is_file():continue
    relative=source.relative_to(OLD)
    target=NEW/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.name=='kernel.macho':
        shutil.copy2(build/'kernel.prelinked.experimental.macho',target)
    elif source.name.endswith(('.data','.system')):
        target.hardlink_to(source)
    else:
        shutil.copy2(source,target)
    # Exact sizes are the ABI of the file table inside the reused firmware.
    assert target.stat().st_size==source.stat().st_size, relative
for entry in media['files']:
    target=NEW/entry['path']
    entry.update(source=str(build/'kernel.prelinked.experimental.macho') if target.name=='kernel.macho' else entry['source'],
        sha256=sha(target),bytes=target.stat().st_size)
media.update(tag='u67',parent_stage=str(OLD),physical_desktop_verified=False,
    host_desktop_verified=False,kernel_change='validated device-tree panic log region; removes incorrect Raspberry Pi physical address',
    firmware_reused_because='All UEFI paths and file lengths unchanged',device_commands_executed=False)
(NEW/'manifest.json').write_text(json.dumps(media,indent=2)+'\n')
manifest=copy.deepcopy(prior)
oldimg=ROOT/'outputs/MIX4-UniXNU-desktop-u65'/prior['artifact']
assert sha(oldimg)==prior['sha256']
image=OUT/'MIX4-UniXNU-desktop-u67-boot.img'
shutil.copy2(oldimg,image)
manifest.update(artifact=image.name,sha256=sha(image),bytes=image.stat().st_size,
    media_root=str(NEW),source_media_manifest=str(NEW/'manifest.json'),
    kernel_sha256=sha(NEW/'esp/EFI/UniXNU/Payloads/kernel.macho'),
    parent_firmware_release='u65',firmware_byte_identical_to_parent=True,
    device_tested=False,physical_desktop_confirmed=False)
for entry in manifest['remote_files']:
    if entry['path'] is None:continue
    oldpath=Path(entry['path'])
    newpath=NEW/oldpath.relative_to(OLD)
    assert newpath.stat().st_size==entry['bytes']
    entry['path']=str(newpath)
assert manifest['kernel_sha256']!=prior['kernel_sha256']
assert (NEW/'esp/EFI/UniXNU/Payloads/kernel.macho.adt').read_bytes()==(OLD/'esp/EFI/UniXNU/Payloads/kernel.macho.adt').read_bytes()
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'SHA256SUMS.txt').write_text(sha(image)+'  '+image.name+'\n'+manifest['kernel_sha256']+'  USB:Payloads/kernel.macho\n')
for name in ('verification.json','platform-progress.patch','native-dt-panic-region.patch','link_kernel.sh'):
    shutil.copy2(build/name,OUT/name)
print(json.dumps({k:manifest[k] for k in ('artifact','sha256','kernel_sha256','firmware_byte_identical_to_parent')},indent=2))
