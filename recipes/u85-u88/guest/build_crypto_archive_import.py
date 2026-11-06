"""Run the upstream crypto builder on a hash-verified immutable archive import.

The only adaptation replaces its Git-checkout provenance check with archive
receipt + per-file verification. Actual compiler, symbols, namespace and POST
logic remain those of the pinned upstream builder.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path('/home/odin/unixnu-odin-build/upstream')
source=ROOT.parent/'corecrypto-reference'
manifest=json.loads((ROOT.parent/'crypto-import.json').read_text())
for name,digest in manifest['files'].items():
    p=source/name
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Immutable source changed: '+name)
actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
if actual!=set(manifest['files']):raise SystemExit('Archive contains unexpected files')
path=ROOT/'scripts/build-corecrypto-14.py'
text=path.read_text()
begin=text.index("if subprocess.check_output(['git', '-C', SOURCE, 'rev-parse'")
end=text.index('OUT.mkdir(',begin)
text=text[:begin]+text[end:]
text=text.replace("SOURCE = ROOT / 'refer/corecrypto-2023'",'SOURCE = Path('+repr(str(source))+')')
sys.path.insert(0,str(ROOT/'scripts'))
(ROOT.parent/'evidence/crypto-builder-adaptation.json').write_text(json.dumps({
    'upstream_builder_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'adaptation':'Git HEAD/status check replaced by archive receipt and exhaustive SHA256 verification',
    'source_receipt':manifest['receipt'],'verified_files':len(actual)},indent=2)+'\n')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
