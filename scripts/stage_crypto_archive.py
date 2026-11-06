"""Stage pinned archive sources with file hashes; never fabricate a Git checkout."""
from pathlib import Path
import hashlib,json,tarfile
ROOT=Path(__file__).resolve().parents[3]
source=ROOT/'work/UniXNU-components/Corecrypto2023-reference-11fba65b12d8830630e248dfa8344caf8b065f26'
out=ROOT/'work/UniXNU-odin/build/offline'
files=sorted(p for p in source.rglob('*') if p.is_file())
manifest={'receipt':json.loads((source/'source-receipt.json').read_text()),
          'files':{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(out/'crypto-import.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(out/'crypto-input.tar.gz','w:gz') as t:
    for p in files:t.add(p,arcname='corecrypto-reference/'+p.relative_to(source).as_posix())
print(len(files),(out/'crypto-input.tar.gz').stat().st_size,flush=True)
