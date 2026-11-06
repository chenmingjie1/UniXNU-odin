"""Apply upstream's storage ABI analysis to our actual iOS16.5 prelink.

The compiled public object is annotation input only. This does not claim live
metaclass or I/O qualification; those require a separate QEMU observation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
upstream = root / 'work/UniXNU-source/UniXNU-04573c510c5fd4892ca6948739389141cc9e05f5'
out = dev / 'build/native-kernel/odin-storage-abi-u12'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel-dir', default='ios16-prelink-u12match')
options = parser.parse_args()
assert options.kernel_dir.replace('-', '').isalnum()
kernel_path = dev / 'build' / options.kernel_dir / 'kernel.prelinked.experimental.macho'
plan_path = kernel_path.parent / 'prelink-emission-report.json'
kit = root / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'
sys.path.insert(0, str(kit))
import native_prelink as np

# Keep the upstream instruction/vtable analysis intact. Its original inputs
# and live metadata checkpoint belong to another OS, so do not reuse them.
source = (upstream / 'scripts/audit-storage-interface.py').read_text()
start = source.index('def require(value, message):')
end = source.index("d = json.loads((ROOT / 'build/darwinboot-storage-native-metadata/gdb-stop.json')")
analysis = source[start:end]
analysis = analysis.replace("['xcrun', 'dwarfdump', '--name=IOBlockStorageDevice', '--show-children', obj_path]", "['unavailable-live-command']")
analysis = analysis.replace("dwarf = subprocess.check_output(['unavailable-live-command'], text=True)", "dwarf = (out / 'class-dwarf.txt').read_text()")
analysis = analysis.replace("(2, 0x110000)", "(2, 0x100500)")
analysis = analysis.replace("Expected iOS 17 reference deployment", "Expected iOS 16.5 reference deployment")
analysis = analysis.replace("kernel_path = ROOT / 'build/xnu-prelink/native-apfs-load-positive.macho'", "kernel_path = supplied_kernel_path")
analysis = analysis.replace("plan = json.loads(kernel_path.with_suffix('.json').read_text())", "plan = json.loads(supplied_plan_path.read_text())")
analysis = analysis.replace('f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7',
                            'e6fa75598f47b5a9460a60913e2ac8e4cd6cd60eb475bb31da65b68ffbcfdad5')
# Once RamBlock is linked, its N_ABS aliases name original base methods.
# They are original imports, not new source-kernel implementations. Exclude
# those aliases when counting inherited native dispatch bindings.
analysis = analysis.replace('exports = np.exports(kernel, native)', '''exports = np.exports(kernel, native)
symbol_command = next(at for cmd, at, size in native['commands'] if cmd == 2)
symoff2, count2, stroff2, _ = struct.unpack_from('<4I', kernel, symbol_command + 8)
original_import_names = set()
for symbol_index in range(count2):
    ix2, kind2, _, _, _ = struct.unpack_from('<IBBHQ', kernel, symoff2 + symbol_index * 16)
    name2 = kernel[stroff2+ix2:kernel.index(b'\\0', stroff2+ix2)].decode()
    if kind2 == 3 and 'IOBlockStorageDevice' in name2:
        original_import_names.add(name2)
exports = {va: [name for name in names if name not in original_import_names] for va, names in exports.items()}
''')
namespace = dict(np=np, out=out, obj_path=out / 'IOBlockStorageDevice-reference.o',
                 supplied_kernel_path=kernel_path, supplied_plan_path=plan_path,
                 re=re, json=json, hashlib=hashlib)
import struct
namespace['struct'] = struct
exec(compile(analysis, 'upstream-storage-analysis-ios16-adapted', 'exec'), namespace)
n = namespace
record = {
    'scope': 'Static actual iOS16.5 ABI comparison; live metadata not yet qualified',
    'target_os': 'iOS 16.5 / 20F66',
    'original_sha256': n['plan']['original_sha256'],
    'candidate_sha256': n['plan']['candidate_sha256'],
    'reference_object_sha256': hashlib.sha256(n['obj']).hexdigest(),
    'reference_executed_or_linked': False,
    'compiled_public_class_size': int(n['class_size'][1], 16),
    'method_slots': len(n['methods']), 'kernel_bindings': n['matched'],
    'pure_virtual_slots': n['methods'].count('___cxa_pure_virtual'),
    'vtable': hex(n['table']), 'original_metaclass': hex(n['meta']),
    'source_ioservice_metaclass': hex(n['service_meta']),
    'original_protected_constructor': hex(n['constructors'][0][0]),
    'original_base_destructor': hex(n['destructor']),
    'abstract_complete_destructors_trap': True,
    'original_executable_code_unchanged': True,
    'live_metadata_verified': False, 'disk_io_verified': False,
    'device_commands_executed': False,
    'methods': [dict(slot=i, reference_name=name, candidate_target=hex(n['pointers'][i]),
                     kernel_names=n['exports'].get(n['pointers'][i], []))
                for i, name in enumerate(n['methods'])],
}
(out / 'interface-static-audit.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k:v for k,v in record.items() if k != 'methods'}, indent=2))
