"""Audit all signed ARM64 Mach-O payloads in a copied host APFS fixture.

This finite exact-file catalog avoids serial runtime discovery of each plugin.
It does not edit any executable, image, signature, or device configuration.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from inspect_root_exec import apfs, audit_file

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
assert not a.output.exists(), 'Preserve previous audit'
a.output.mkdir(parents=True)
container = apfs.Container(a.image)
volume = apfs.pick_volume(container, None)
signed, unsigned, non_arm, non_macho = [], [], [], 0
regular = 0

def walk(oid, prefix):
    global regular, non_macho
    for name, child_oid, dtype in volume.dir_entries(oid):
        path = prefix + '/' + name
        if dtype == 4:
            walk(child_oid, path)
        elif dtype == 8:
            inode = volume.inode(child_oid)
            assert inode.is_reg
            regular += 1
            data = inode.contents()
            magic = data[:4]
            if magic not in (bytes.fromhex('cffaedfe'), bytes.fromhex('cafebabe')):
                non_macho += 1
                continue
            if magic == bytes.fromhex('cffaedfe') and struct.unpack_from('<I', data, 4)[0] != 0x100000c:
                non_arm.append(path)
                continue
            report = audit_file(data, path)
            if report['code_directories']:
                assert all(not cd['page_hash_mismatches'] for cd in report['code_directories']), path
                signed.append(report)
            else:
                unsigned.append(dict(path=path, sha256=report['sha256']))
            if len(signed) % 100 == 0:
                print('Audited signed ARM64 files:', len(signed), flush=True)

walk(2, '')
container.close()
assert len(signed) > 600
(a.output / 'verification.json').write_text(json.dumps(signed, indent=2) + '\n')
with a.image.open('rb') as stream:
    image_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
record = dict(scope='Computer-only exact original Mach-O catalog; not wildcard trust or Apple attestation',
    image=str(a.image), image_sha256=image_hash, regular_files=regular,
    signed_macho_files=len(signed), signed_code_pages=sum(cd['code_slots'] for r in signed for cd in r['code_directories']),
    non_macho_files=non_macho, unsigned_macho_files=unsigned, other_cpu_files=non_arm,
    all_signed_page_hashes_verified=True, executables_modified=False,
    signature_checks_disabled=False, device_commands_executed=False)
(a.output / 'catalog.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
