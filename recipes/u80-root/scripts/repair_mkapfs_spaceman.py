"""Repair the missing empty tier-2 address offset in a copied mkapfs image.

Apple APFS 2142 validates both device address-table offsets even when tier 2
has no blocks. HakiOS mkapfs leaves the second offset zero. Only that field
and the spaceman checksum are changed; no kernel policy or file data changes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct


def checksum(data):
    a = b = 0
    mod = 0xffffffff
    for value, in struct.iter_unpack('<I', data[8:]):
        a = (a + value) % mod
        b = (b + a) % mod
    first = mod - ((a + b) % mod)
    second = mod - ((a + first) % mod)
    return first | second << 32


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def repair(source, target):
    assert source.resolve() != target.resolve() and not target.exists()
    modifications = []
    with source.open('rb') as stream:
        nx = stream.read(4096)
        assert nx[32:36] == b'NXSB' and struct.unpack_from('<I', nx, 36)[0] == 4096
        assert checksum(nx) == int.from_bytes(nx[:8], 'little')
        assert struct.unpack_from('<Q', nx, 40)[0] * 4096 == source.stat().st_size
        desc_blocks, = struct.unpack_from('<I', nx, 104)
        desc_base, = struct.unpack_from('<Q', nx, 112)
        assert 0 < desc_blocks <= 65536
        for index in range(desc_blocks):
            stream.seek((desc_base + index) * 4096)
            block = stream.read(4096)
            if len(block) != 4096 or struct.unpack_from('<I', block, 24)[0] != 0x4000000c:
                continue
            assert checksum(block) == int.from_bytes(block[:8], 'little')
            count, = struct.unpack_from('<I', block, 36)
            assert count <= (4096 - 40) // 40
            for entry in range(count):
                kind, subtype, size, pad, fs_oid, oid, physical = struct.unpack_from('<IIIIQQQ', block, 40 + 40 * entry)
                if kind != 0x80000005:
                    continue
                assert subtype == pad == fs_oid == 0 and size % 4096 == 0 and 0 < size <= 65536
                stream.seek(physical * 4096)
                before = stream.read(size)
                assert len(before) == size and checksum(before) == int.from_bytes(before[:8], 'little')
                assert struct.unpack_from('<Q', before, 8)[0] == oid
                assert not any(before[0x60:0x80]) and struct.unpack_from('<I', before, 0x80)[0] == 0, 'Only an empty tier-2 device is repairable'
                cibs, cabs = struct.unpack_from('<II', before, 0x40)
                main_offset, = struct.unpack_from('<I', before, 0x50)
                tier2_offset = main_offset + 8 * (cabs if cabs else cibs)
                assert 0x150 <= main_offset < tier2_offset <= size
                after = bytearray(before)
                struct.pack_into('<I', after, 0x80, tier2_offset)
                struct.pack_into('<Q', after, 0, checksum(after))
                assert after[8:0x80] == before[8:0x80] and after[0x84:] == before[0x84:]
                modifications.append((physical * 4096, before, bytes(after)))
    assert modifications, 'No matching synthetic spaceman was found'
    assert len({off for off, _, _ in modifications}) == len(modifications)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    with target.open('r+b') as stream:
        for offset, before, after in modifications:
            stream.seek(offset)
            assert stream.read(len(before)) == before
            stream.seek(offset)
            stream.write(after)
    # Independently compare every byte outside the permitted fields.
    with source.open('rb') as left, target.open('rb') as right:
        offset = 0
        while original := left.read(1024 * 1024):
            changed = right.read(len(original))
            if changed != original:
                allowed = {off + n for off, _, _ in modifications for n in (*range(8), *range(0x80, 0x84))}
                assert all(offset + n in allowed for n, (a, b) in enumerate(zip(original, changed)) if a != b)
            offset += len(original)
        assert not right.read(1)
    report = {'source': str(source), 'source_sha256': digest(source),
              'output': str(target), 'output_sha256': digest(target),
              'bytes': target.stat().st_size,
              'modifications': [{'spaceman_offset': off,
                  'tier2_address_table_offset': struct.unpack_from('<I', after, 0x80)[0]}
                  for off, before, after in modifications],
              'file_data_unchanged': True, 'kernel_code_changed': False,
              'device_commands_executed': False, 'mount_verified': False,
              'basis': 'Unmodified APFS 2142.122.2 spaceman validation at VA 0xfffffff00524f5e0; local QEMU captured expected geometry'}
    target.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    print(json.dumps(repair(args.source, args.target), indent=2))
