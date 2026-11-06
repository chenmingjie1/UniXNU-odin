"""Recover actual ObjC method names for stripped functions in observed UI stacks."""
from pathlib import Path
import argparse
import json
import struct
from inspect_cache_objc_refs import Cache, DEFAULT, pointer, cstring

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--image', required=True)
p.add_argument('--address', type=lambda value: int(value, 0), action='append', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
c = Cache(DEFAULT)
image = next(i for i in c.images if i.name.endswith(a.image))
region = struct.unpack_from('<Q', c.files[0][1], 224)[0]
opt = region + struct.unpack_from('<Q', c.files[0][1], 464)[0]
assert struct.unpack('<I', c.read(opt, 4))[0] == 1
selector_base = region + struct.unpack('<Q', c.read(opt + 48, 8))[0]
targets = {int(c.resolve(address)['symbol_address'], 16): address for address in a.address}
found, errors = [], []


def methods(address, owner, kind):
    if not address:
        return
    flags, count = struct.unpack('<2I', c.read(address, 8))
    stride = flags & 0xfffc
    assert count < 10000 and stride in (12, 24), (owner, hex(address), flags, count)
    for index in range(count):
        entry = address + 8 + stride * index
        if flags & 0x80000000:
            rel = struct.unpack('<3i', c.read(entry, 12))
            imp = entry + 8 + rel[2]
            if imp not in targets:
                continue
            selector = selector_base + struct.unpack('<I', c.read(entry, 4))[0] if flags & 0x40000000 else pointer(c, entry + rel[0])
        else:
            imp = pointer(c, entry + 16)
            if imp not in targets:
                continue
            selector = pointer(c, entry)
        found.append(dict(requested=hex(targets[imp]), implementation=hex(imp),
            owner=owner, kind=kind, selector=cstring(c, selector)))


for (_, section), (start, size) in image.sections.items():
    if section not in ('__objc_classlist', '__objc_catlist'):
        continue
    for at in range(start, start + size, 8):
        address = pointer(c, at)
        try:
            if section == '__objc_classlist':
                ro = pointer(c, address + 32) & ~7
                name = cstring(c, pointer(c, ro + 24))
                methods(pointer(c, ro + 32), name, '-')
                meta = pointer(c, address)
                ro = pointer(c, meta + 32) & ~7
                methods(pointer(c, ro + 32), name, '+')
            else:
                name = cstring(c, pointer(c, address))
                methods(pointer(c, address + 16), 'category:' + name, '-')
                methods(pointer(c, address + 24), 'category:' + name, '+')
        except (AssertionError, ValueError, UnicodeError, StopIteration) as error:
            errors.append(dict(address=hex(address), error=str(error)))
c.close()
record = dict(image=image.name, methods=found, errors=errors,
    unresolved=[hex(address) for imp, address in targets.items() if not any(int(row['implementation'],16)==imp for row in found)],
    original_files_modified=False, device_commands_executed=False)
a.output.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
