"""Build an explicit v2 owner development trust cache from audited files.

This is not Apple attestation. Each file must still match its audit hash,
and every CodeDirectory used must have passed all recorded page hashes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import uuid
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit', type=Path, action='append', required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--image', type=Path, help='Re-read audited cache files directly from this APFS image')
args = parser.parse_args()
volume = None
container = None
if args.image:
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root/'work/hakios-upstream/tools/apfs'))
    import apfs
    class BinaryImage:
        def __init__(self, path):
            self.stream = open(path, 'rb')
            self.size = Path(path).stat().st_size
        def read(self, offset, length):
            self.stream.seek(offset)
            return self.stream.read(length)
        def close(self):
            self.stream.close()
    apfs.RawImage = BinaryImage
    container = apfs.Container(args.image)
    volume = apfs.pick_volume(container, None)
entries = set()
files = []
for audit in args.audit:
    for row in json.loads(audit.read_text()):
        target = audit.parent/row['path'].lstrip('/')
        if target.exists():
            data = target.read_bytes()
        else:
            assert volume is not None
            data = volume.inode(volume.lookup(row['path'])[0]).contents()
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        for directory in row['code_directories']:
            assert directory['page_hash_mismatches'] == []
            cdhash = bytes.fromhex(directory['cdhash'])
            assert len(cdhash) == 20 and directory['hash_type'] in (1, 2, 3, 4)
            entries.add(cdhash + struct.pack('<4B', directory['hash_type'], 0, 0, 0))
        files.append({'path': row['path'], 'sha256': row['sha256'],
                      'signed': bool(row['code_directories'])})
        del data
if container:container.close()
assert entries
ordered = sorted(entries)
identifier = hashlib.sha256(b'UniXNU.odin.LocalDevelopmentTrust.v1\0' + b''.join(ordered)).digest()[:16]
module = struct.pack('<I16sI', 2, identifier, len(ordered)) + b''.join(ordered)
bundle = struct.pack('<II', 1, 8) + module
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(bundle)
receipt = {'domain': 'Local owner development; not Apple attestation',
           'sha256': hashlib.sha256(bundle).hexdigest(), 'bytes': len(bundle),
           'uuid': str(uuid.UUID(bytes=identifier)), 'entries': [e.hex() for e in ordered],
           'files': files, 'scope': 'Only audited signed files; no wildcard trust'}
args.output.with_suffix('.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt, indent=2))
