"""Use the upstream pthread compiler with honest archive provenance."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile
ROOT=Path('/home/odin/unixnu-odin-build/upstream')
source=ROOT.parent/'pthread-reference'
manifest=json.loads((ROOT.parent/'pthread-import.json').read_text())
for name,digest in manifest['files'].items():
 if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Source changed: '+name)
if {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}!=set(manifest['files']):
 raise SystemExit('Unexpected pthread input')
work=Path(tempfile.mkdtemp(prefix='libpthread-archive-',dir=ROOT/'.cache'))
shutil.copytree(source,work,dirs_exist_ok=True)
patches=[]
for patch in sorted((ROOT.parent/'device/patches/libpthread').glob('*.patch')):
 subprocess.run(['git','apply','--check',str(patch)],cwd=work,check=True)
 subprocess.run(['git','apply',str(patch)],cwd=work,check=True)
 patches.append({'name':patch.name,'sha256':hashlib.sha256(patch.read_bytes()).hexdigest()})
path=ROOT/'scripts/build-libpthread-kernel.py'
text=path.read_text();begin=text.index("if subprocess.check_output(['git', '-C', SOURCE, 'rev-parse'")
end=text.index('SOURCE = WORK',begin)
text=text[:begin]+'WORK = Path('+repr(str(work))+')\n'+text[end:]
# The 16.5 SDK predates Vision. This target is explicitly iOS, not Vision.
text=text.replace("'-D__PTHREAD_EXPOSE_INTERNALS__=1'", "'-DTARGET_OS_VISION=0', '-D__PTHREAD_EXPOSE_INTERNALS__=1'")
text=text.replace("'-std=gnu11'", "'-include', '/home/odin/xnu-work/project/xnu-deps/hostinc/xnu_clang_compat.h', '-std=gnu11'")
sys.path.insert(0,str(ROOT/'scripts'))
(ROOT.parent/'evidence/pthread-builder-adaptation.json').write_text(json.dumps({
 'upstream_builder_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'source_receipt':manifest['receipt'],'verified_files':len(manifest['files']),'patches':patches,
 'adaptation':'Archive receipt and file hashes instead of Git clone/HEAD; ordered patches strictly checked'},indent=2)+'\n')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
