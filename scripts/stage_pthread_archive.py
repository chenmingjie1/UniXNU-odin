from pathlib import Path
import hashlib,json,tarfile,shutil
ROOT=Path(__file__).resolve().parents[3]
src=ROOT/'work/UniXNU-components/Libpthread519-reference-c0e60fb5ecfc54cf379c261d3f9572cc22ded891'
out=ROOT/'work/UniXNU-odin/build/offline'
files=sorted(p for p in src.rglob('*') if p.is_file())
(out/'pthread-import.json').write_text(json.dumps({'receipt':json.loads((src/'source-receipt.json').read_text()),
 'files':{p.relative_to(src).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
patch=ROOT/'work/UniXNU-components/Reference-nx769j-2a265afdbd95d45e4a90664157e793c3bfee3755/patches/libpthread'
dest=ROOT/'work/UniXNU-odin/patches/libpthread'
shutil.copytree(patch,dest,dirs_exist_ok=True)
with tarfile.open(out/'pthread-input.tar.gz','w:gz') as t:
 for p in files:t.add(p,arcname='pthread-reference/'+p.relative_to(src).as_posix())
 t.add(dest,arcname='device/patches/libpthread')
print(len(files),(out/'pthread-input.tar.gz').stat().st_size)
