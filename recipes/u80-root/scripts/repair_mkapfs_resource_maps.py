"""Repair synthetic type-4 maps for the original iOS 16.5 decompressor.

The original driver compares the final 50-byte map with its fixed template.
The synthetic writer copied the variable fork header into the first 16 bytes;
this driver requires zeros there. Only that unused map-header copy changes.
The fork header, compressed pieces, extent metadata and code signatures stay.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'upstream/apfs'))
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

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def mapped_bytes(path, address, count):
    data = path.read_bytes()
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 25:
            va, _, at, backed = struct.unpack_from('<4Q', data, offset+24)
            if va <= address and address+count <= va+backed:
                return data[at+address-va:at+address-va+count]
        offset += size
    raise ValueError('Expected map is not file backed')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('target', type=Path)
parser.add_argument('--kernel', type=Path, required=True)
args = parser.parse_args()
assert args.source.resolve() != args.target.resolve() and not args.target.exists()
expected = bytes.fromhex('000000000000000000000000000000000000000000000000001c00320000636d70660000000a0001ffff0000000000000000')
assert mapped_bytes(args.kernel, 0xfffffff004403d58, 50) == expected
container = apfs.Container(args.source)
volume = apfs.pick_volume(container, None)
compressed, forks, extents = set(), {}, {}
for key, value in volume.tree.iter_all():
    packed, = struct.unpack_from('<Q', key)
    kind, oid = packed >> apfs.OBJ_TYPE_SHIFT, packed & apfs.OBJ_ID_MASK
    if kind == apfs.TYPE_XATTR:
        name = key[10:].split(b'\0', 1)[0]
        flags, length = struct.unpack_from('<HH', value)
        data = value[4:4+length]
        if name == b'com.apple.decmpfs' and flags & apfs.XATTR_DATA_EMBEDDED:
            magic, codec = struct.unpack_from('<II', data)
            if magic == apfs.DECMPFS_MAGIC and codec == 4:
                compressed.add(oid)
        if name == b'com.apple.ResourceFork' and flags & apfs.XATTR_DATA_STREAM:
            forks[oid] = struct.unpack_from('<QQ', data)
    elif kind == apfs.TYPE_FILE_EXTENT:
        logical, = struct.unpack_from('<Q', key, 8)
        length_flags, physical, _ = struct.unpack_from('<QQQ', value)
        extents.setdefault(oid, []).append((logical, length_flags & apfs.J_FILE_EXTENT_LEN_MASK, physical))

def physical_offset(sid, logical, length):
    matches = [physical*container.block_size + logical-start
               for start, count, physical in extents[sid]
               if physical and start <= logical and logical+length <= start+count]
    assert len(matches) == 1, (sid, logical, length)
    return matches[0]

modifications = []
for oid in sorted(compressed):
    sid, size = forks[oid]
    assert size >= 50
    start = physical_offset(sid, 0, 16)
    at = physical_offset(sid, size-50, 50)
    header = container.image.read(start, 16)
    before = container.image.read(at, 50)
    assert before[16:] == expected[16:]
    assert before[:16] == header or before[:16] == bytes(16)
    if before[:16] != bytes(16):
        modifications.append({'inode': oid, 'stream': sid, 'offset': at,
                              'before': before[:16].hex(), 'after': bytes(16).hex()})
container.close()
assert modifications
assert len({row['offset'] for row in modifications}) == len(modifications)
args.target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(args.source, args.target)
with args.target.open('r+b') as stream:
    for row in modifications:
        stream.seek(row['offset'])
        assert stream.read(16).hex() == row['before']
        stream.seek(row['offset'])
        stream.write(bytes(16))

# Compare every byte outside the small, explicitly permitted metadata copies.
with args.source.open('rb') as left, args.target.open('rb') as right:
    cursor = 0
    for row in sorted(modifications, key=lambda r:r['offset']):
        remaining = row['offset'] - cursor
        assert remaining >= 0
        while remaining:
            count = min(remaining, 1024*1024)
            assert left.read(count) == right.read(count)
            remaining -= count
        assert left.read(16).hex() == row['before'] and right.read(16) == bytes(16)
        cursor = row['offset'] + 16
    while chunk := left.read(1024*1024):
        assert chunk == right.read(len(chunk))
    assert not right.read(1)
report = {'source': str(args.source), 'source_sha256': digest(args.source),
          'output': str(args.target), 'output_sha256': digest(args.target),
          'bytes': args.target.stat().st_size, 'type4_files': len(compressed),
          'maps_repaired': len(modifications), 'modifications': modifications,
          'all_other_image_bytes_identical': True,
          'kernel_sha256': digest(args.kernel),
          'original_driver_template_va': '0xfffffff004403d58',
          'expected_map': expected.hex(),
          'device_commands_executed': False, 'runtime_verified': False}
args.target.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k != 'modifications'}, indent=2))
