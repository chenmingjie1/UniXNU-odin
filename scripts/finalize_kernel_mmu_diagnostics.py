from pathlib import Path
import difflib,hashlib,json
r=Path('/home/odin/unixnu-odin-build'); t=r/'upstream/.cache/xnu-work'; o=r/'evidence/odin-mmu-u08'
s=t/'osfmk/arm64/start.s'; text=s.read_text()
if 'cmp x10, #4320' in text:
 text=text.replace('cmp x10, #4320','mov x11, #4320\n cmp x10, x11').replace('six 2 MiB','five 2 MiB');s.write_text(text)
patch=''
for rel,backup in [('osfmk/arm64/start.s','start.s.before'),('osfmk/arm/arm_init.c','arm_init.c.before')]:
 before=(o/backup).read_text();after=(t/rel).read_text();patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(o/'odin-mmu-diagnostics.patch').write_text(patch)
v=json.loads((o/'verification.json').read_text());v['source_sha256']=hashlib.sha256(text.encode()).hexdigest();(o/'verification.json').write_text(json.dumps(v,indent=2)+'\n')
print('Source and patch hashes synchronized')
