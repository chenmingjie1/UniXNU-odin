"""Reuse full desktop media and u67 native kernel; change only the core handoff."""
from pathlib import Path
import copy,hashlib,json,shutil,struct
from adt_codec import decode,encode,lookup
DEV=Path(__file__).resolve().parents[1]
OLD=DEV/'build/device-desktop-u67';NEW=DEV/'build/device-desktop-u69'
assert not NEW.exists(), 'Preserve completed stages; select a new release instead'
NEW.mkdir()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8<<20),b''):h.update(chunk)
    return h.hexdigest()
media=copy.deepcopy(json.loads((OLD/'manifest.json').read_text()))
changes=[]
for source in sorted((OLD/'esp').rglob('*')):
    if not source.is_file():continue
    target=NEW/source.relative_to(OLD);target.parent.mkdir(parents=True,exist_ok=True)
    if source.name.endswith(('.data','.system')):target.hardlink_to(source)
    elif source.name=='DarwinBoot.efi':shutil.copy2(DEV/'build/darwinboot-u69/DarwinBoot.efi',target)
    elif source.name.endswith('.adt'):
        tree=decode(source.read_bytes());cpu=lookup(tree,'cpus','cpu0')
        before={k:v.hex() for k,v in cpu.items()}
        cpu['reg']=struct.pack('<I',0x700)
        cpu['cpu-id']=struct.pack('<I',0)
        cpu['state']=b'running\0';cpu['compatible']=b'arm,cortex-x1\0'
        target.write_bytes(encode(tree))
        changes.append(dict(node='/cpus/cpu0',before=before,after={k:v.hex() for k,v in cpu.items()}))
    elif source.name=='unixnu.toml':
        text=source.read_text().replace('timeout = 10','timeout = 0')
        text=text.replace('MIX 4 - UniXNU desktop candidate (unqualified)','MIX 4 - UniXNU / resident core7')
        target.write_text(text)
    else:shutil.copy2(source,target)
for item in media['files']:
    target=NEW/item['path'];item.update(sha256=sha(target),bytes=target.stat().st_size)
media.update(tag='u69',parent_stage=str(OLD),physical_desktop_verified=False,
    host_desktop_verified=False,device_commands_executed=False,
    handoff='HakiOS-derived core0 resident / PSCI SMC core7 0x700, no ExitBootServices',
    kernel_change='none; retain u67 native kernel with validated DT panic region',adt_changes=changes)
assert sha(NEW/'esp/EFI/UniXNU/Payloads/kernel.macho')=='1c598f29257c39d819cb1ca1cab8d6c0658d9b9090bde12a8581d9105ab093d4'
(NEW/'manifest.json').write_text(json.dumps(media,indent=2)+'\n')
print(json.dumps(dict(stage=str(NEW),adt_changes=changes),indent=2))
