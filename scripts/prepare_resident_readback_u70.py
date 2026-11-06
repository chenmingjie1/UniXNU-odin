"""Reuse u69 full-system inputs; add read-only kernel/framebuffer host access."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--release',default='u70');parser.add_argument('--parent',default='u69');parser.add_argument('--kernel',type=Path)
parser.add_argument('--system',type=Path);parser.add_argument('--trust-cache',type=Path);options=parser.parse_args()
assert options.release.isalnum() and options.parent.isalnum()
DEV=Path(__file__).resolve().parents[1]
OLD=DEV/('build/device-desktop-'+options.parent);NEW=DEV/('build/device-desktop-'+options.release)
assert not NEW.exists();NEW.mkdir()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
manifest=copy.deepcopy(json.loads((OLD/'manifest.json').read_text()))
for source in sorted((OLD/'esp').rglob('*')):
 if not source.is_file():continue
 target=NEW/source.relative_to(OLD);target.parent.mkdir(parents=True,exist_ok=True)
 if source.name=='kernel.macho.system' and options.system:target.hardlink_to(options.system.resolve())
 elif source.name=='kernel.macho.trustcache' and options.trust_cache:shutil.copy2(options.trust_cache,target)
 elif source.name.endswith(('.data','.system')):target.hardlink_to(source)
 elif source.name=='DarwinBoot.efi':shutil.copy2(DEV/('build/darwinboot-'+options.release+'/DarwinBoot.efi'),target)
 elif source.name=='kernel.macho' and options.kernel:shutil.copy2(options.kernel,target)
 else:shutil.copy2(source,target)
for item in manifest['files']:
 target=NEW/item['path'];item.update(sha256=sha(target),bytes=target.stat().st_size)
 if target.name=='kernel.macho' and options.kernel:item['source']=str(options.kernel.resolve())
 if target.name=='kernel.macho.system' and options.system:item['source']=str(options.system.resolve())
 if target.name=='kernel.macho.trustcache' and options.trust_cache:item['source']=str(options.trust_cache.resolve())
manifest.update(tag=options.release,parent_stage=str(OLD),device_commands_executed=False,
 physical_desktop_verified=False,host_desktop_verified=False,
 change='Keep full desktop boot; expose fixed kernel symbols and GOP framebuffer through read-only resident USB')
(NEW/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(NEW)
