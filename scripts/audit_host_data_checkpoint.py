"""Read checkpoint capacity and real migration markers from host RAM Data.

No mount, write, phone query or migration-complete marker injection occurs.
"""
from pathlib import Path
import argparse
import json
import plistlib
import struct
from inspect_root_exec import apfs

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
assert not a.output.exists()
c = apfs.Container(a.image)
v = apfs.pick_volume(c, None)
spaces = []
for index in range(c.nx['xp_desc_blocks']):
    block = c.blocks.raw(c.nx['xp_desc_base'] + index)
    if not apfs.checksum_ok(block):
        continue
    oid, xid, kind, subtype = apfs.obj_hdr(block)
    if kind != 0x4000000c or xid != c.xid:
        continue
    count = struct.unpack_from('<I', block, 36)[0]
    assert count <= (c.block_size - 40) // 40
    for entry in range(count):
        kind, _, size, _, _, oid, physical = struct.unpack_from('<IIIIQQQ', block, 40 + entry * 40)
        if kind == 0x80000005 and oid == c.nx['spaceman_oid']:
            raw = c.image.read(physical * c.block_size, size)
            assert apfs.checksum_ok(raw)
            device_blocks = struct.unpack_from('<Q', raw, 48)[0]
            free_blocks = struct.unpack_from('<Q', raw, 72)[0]
            assert 0 <= free_blocks <= device_blocks <= c.nx['block_count']
            spaces.append(dict(checkpoint=xid, physical=physical,
                device_blocks=device_blocks, free_blocks=free_blocks,
                free_bytes=free_blocks*c.block_size))
markers = {}
for path in ('/mobile/Library/Preferences/com.apple.DataMigration.plist',
             '/mobile/Library/Preferences/com.apple.migration.plist'):
    hit = v.lookup(path)
    markers[path] = plistlib.loads(v.inode(hit[0]).contents()) if hit else None
record = dict(image=str(a.image), checkpoint=c.xid,
    container_bytes=c.nx['block_count']*c.block_size,
    volume_files=v.num_files, volume_directories=v.num_directories,
    volume_blocks_allocated=v.blocks_alloced, space_manager=spaces,
    actual_migration_preferences=markers, image_modified=False,
    device_commands_executed=False)
c.close()
a.output.write_text(json.dumps(record, indent=2, default=str)+'\n')
print(json.dumps(record, indent=2, default=str))
