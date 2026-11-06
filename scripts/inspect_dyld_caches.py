"""Audit every actual shared-cache CodeDirectory in the copied APFS root."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'work/hakios-upstream/tools/apfs'))
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
container = apfs.Container(args.image)
volume = apfs.pick_volume(container, None)
directory = '/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld'
reports = []
for name, oid, kind in sorted(volume.dir_entries(volume.lookup(directory)[0])):
    if not name.startswith('dyld_shared_cache_arm64') or name.endswith('.symbols'):
        continue
    data = volume.inode(oid).contents()
    assert data[:16] == b'dyld_v1   arm64\0', name
    start, length = struct.unpack_from('<QQ', data, 40)
    assert start+length <= len(data)
    magic, total, count = struct.unpack_from('>III', data, start)
    assert magic == 0xfade0cc0 and total <= length
    row = {'path':directory+'/'+name, 'bytes':len(data),
           'sha256':hashlib.sha256(data).hexdigest(), 'uuid':data[88:104].hex(),
           'code_directories':[]}
    for index in range(count):
        slot, relative = struct.unpack_from('>II', data, start+12+index*8)
        position = start+relative
        blob_magic, blob_size = struct.unpack_from('>II', data, position)
        if blob_magic != 0xfade0c02:
            continue
        blob = data[position:position+blob_size]
        version, flags, hash_at, identifier, special, codes, limit = struct.unpack_from('>7I',blob,8)
        hash_size, hash_type, platform, page_shift = struct.unpack_from('>4B',blob,36)
        algorithm = {1:'sha1',2:'sha256',3:'sha256',4:'sha384'}[hash_type]
        page = 1 << page_shift
        assert codes == (limit+page-1)//page
        assert hash_at+codes*hash_size <= blob_size
        if version >= 0x20100:
            assert struct.unpack_from('>I',blob,44)[0] == 0, 'Scatter signatures need a separate audit'
        mismatches = []
        for slot_index in range(codes):
            expected = blob[hash_at+slot_index*hash_size:hash_at+(slot_index+1)*hash_size]
            actual = hashlib.new(algorithm,data[slot_index*page:min((slot_index+1)*page,limit)]).digest()[:hash_size]
            if actual != expected:mismatches.append(slot_index)
        row['code_directories'].append({'slot_type':slot, 'version':hex(version),
            'flags':hex(flags), 'identifier':blob[identifier:].split(b'\0')[0].decode(errors='replace'),
            'hash_type':hash_type, 'hash_size':hash_size, 'page_shift':page_shift,
            'code_limit':limit, 'code_slots':codes,
            'cdhash':hashlib.new(algorithm,blob).digest()[:20].hex(),
            'page_hash_mismatches':mismatches})
        assert not mismatches, name
    assert row['code_directories'], name
    reports.append(row)
    print(name, 'verified pages', sum(r['code_slots'] for r in row['code_directories']), flush=True)
    del data
container.close()
assert len(reports) == 43
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(reports,indent=2)+'\n')
print('PASS: all original signature pages of 43 cache files; no code or trust changes')
