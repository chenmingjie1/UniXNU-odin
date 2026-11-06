"""Check actual compiled iOS16 display ABI against all original dispatch slots."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build-dir',type=Path,default=DEV/'build/display-analysis-ios16')
p.add_argument('--source-dir',type=Path,default=DEV/'drivers/OdinDisplay')
a=p.parse_args()
OUT = a.build_dir
SRC = a.source_dir
sys.path.insert(0, str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

contract = json.loads((SRC/'interface-contract.json').read_text())
receipt = json.loads((OUT/'compile-receipt.json').read_text())
for filename, digest in receipt['files'].items():
    path = (SRC if (SRC/filename).exists() else OUT)/filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, filename
assert not receipt['linked'] and not receipt['executed']
obj = (OUT/'OdinDisplayABIAnnotation.o').read_bytes()
image = np.macho(obj)
assert image['kind'] == 1
version = next(at for cmd, at, size in image['commands'] if cmd == 0x32)
assert struct.unpack_from('<II', obj, version+8) == (2, 0x100500)
dwarf = (OUT/'class-dwarf.txt').read_text()
for name in ('OdinDisplayABIAnnotation', 'IOMobileFramebufferLegacy'):
    size = re.search(r'DW_AT_name\s+\("'+name+r'"\)[\s\S]{0,250}?DW_AT_byte_size\s+\((0x[0-9a-f]+)\)', dwarf)
    assert size and int(size[1], 16) == 0x1660, name
symcmd = next(at for cmd, at, size in image['commands'] if cmd == 2)
symoff, count, stroff, _ = struct.unpack_from('<4I', obj, symcmd+8)
symbols = []
for i in range(count):
    ix, kind, section, desc, value = struct.unpack_from('<IBBHQ', obj, symoff+i*16)
    name = obj[stroff+ix:obj.index(b'\0', stroff+ix)].decode()
    symbols.append(dict(name=name, kind=kind, value=value))
table = next(s['value'] for s in symbols if s['name'].startswith('__ZTV') and s['name'].endswith('OdinDisplayABIAnnotation'))
relocations = {}
for segment in image['segments']:
    for section in segment['sections']:
        if section['va'] <= table < section['va']+section['size']:
            ro, rc = struct.unpack_from('<II', obj, section['command_offset']+56)
            for i in range(rc):
                address, word = struct.unpack_from('<II', obj, ro+i*8)
                if word >> 27 & 1 and word >> 28 == 0 and word >> 25 & 3 == 3:
                    relocations[section['va']+address] = symbols[word & 0xffffff]['name']
compiled = [relocations.get(table+16+i*8) for i in range(338)]
assert all(compiled) and table+16+338*8 not in relocations
kernel = (DEV/'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
assert hashlib.sha256(kernel).hexdigest() == contract['candidate_sha256']
native = np.macho(kernel)
native_names = {name: address for address, group in np.exports(kernel, native).items() for name in group}
owned = []
bindings = {}
inherited = 0
for i, (name, expected) in enumerate(zip(compiled, contract['expected_dispatch'])):
    assert expected['slot'] == i
    if 'OdinDisplayABIAnnotation' in name:
        assert i in [0, 1, 7]+contract['abstract_slots'], (i, name)
        owned.append(i)
    elif '25IOMobileFramebufferLegacy' in name:
        assert i not in contract['abstract_slots']
        address = int(expected['address'], 16)
        assert name not in bindings or bindings[name] == address
        bindings[name] = address
    else:
        assert i < 168 and native_names.get(name) == int(expected['address'], 16), (i, name)
        inherited += 1
assert owned == sorted([0, 1, 7]+contract['abstract_slots'])
bindings.update({
    '__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass': int(contract['protected_constructor'], 16),
    '__ZN25IOMobileFramebufferLegacyD2Ev': int(contract['base_destructor'], 16),
    '__ZN25IOMobileFramebufferLegacy10gMetaClassE': int(contract['metaclass'], 16),
    '__ZTV25IOMobileFramebufferLegacy': int(contract['vtable'], 16),
})
unresolved = [s['name'] for s in symbols if s['kind'] == 1 and '25IOMobileFramebufferLegacy' in s['name']]
assert all(name in bindings for name in unresolved), [s for s in unresolved if s not in bindings]

# Independently inspect the actual staged GOP backend, not just the annotation.
backend = (OUT/'OdinLegacyGOPDisplay.o').read_bytes()
backend_image = np.macho(backend)
backend_symcmd = next(at for cmd,at,size in backend_image['commands'] if cmd == 2)
bsy, bcount, bst, _ = struct.unpack_from('<4I', backend, backend_symcmd+8)
backend_symbols = []
for i in range(bcount):
    ix, kind, section, desc, value = struct.unpack_from('<IBBHQ', backend, bsy+i*16)
    name = backend[bst+ix:backend.index(b'\0', bst+ix)].decode()
    backend_symbols.append(dict(name=name,kind=kind,value=value))
backend_table = next(s['value'] for s in backend_symbols if s['name'].startswith('__ZTV') and s['name'].endswith('OdinLegacyGOPDisplay'))
backend_relocations = {}
for segment in backend_image['segments']:
    for section in segment['sections']:
        if section['va'] <= backend_table < section['va']+section['size']:
            ro, rc = struct.unpack_from('<II', backend, section['command_offset']+56)
            for i in range(rc):
                address, bits = struct.unpack_from('<II', backend, ro+i*8)
                if bits >> 27 & 1 and bits >> 28 == 0 and bits >> 25 & 3 == 3:
                    backend_relocations[section['va']+address] = backend_symbols[bits & 0xffffff]['name']
backend_methods = [backend_relocations.get(backend_table+16+i*8) for i in range(338)]
assert all(backend_methods) and backend_table+16+338*8 not in backend_relocations
backend_owned = []
for i, (name, expected) in enumerate(zip(backend_methods,contract['expected_dispatch'])):
    if 'OdinLegacyGOPDisplay' in name:
        assert i in [0,1,7,14,87,155,188,274,276,282]+contract['abstract_slots'], (i,name)
        backend_owned.append(i)
    else:
        assert bindings.get(name,native_names.get(name)) == int(expected['address'],16), (i,name)
expected_backend_owned=[0,1,7,14,274]+contract['abstract_slots']
if 'getDotPitch' in backend_methods[188]:expected_backend_owned.append(188)
if 'validateSwap' in backend_methods[282]:expected_backend_owned.append(282)
logical_pm='bool logicalPM=false;' in (SRC/'OdinLegacyGOPDisplay.cpp').read_text()
if logical_pm:expected_backend_owned += [87,155]
cpu_present='const void *validatedRequest=nullptr;' in (SRC/'OdinLegacyGOPDisplay.cpp').read_text()
if cpu_present:expected_backend_owned.append(276)
assert backend_owned == sorted(expected_backend_owned)
backend_unresolved = [s['name'] for s in backend_symbols if s['kind'] == 1 and '25IOMobileFramebufferLegacy' in s['name']]
assert all(name in bindings for name in backend_unresolved), backend_unresolved
backend_size = re.search(r'DW_AT_name\s+\("OdinLegacyGOPDisplay"\)[\s\S]{0,250}?DW_AT_byte_size\s+\((0x[0-9a-f]+)\)',
    (OUT/'backend-class-dwarf.txt').read_text())
expected_backend_bytes=0x1678 if cpu_present else 0x1670 if logical_pm else 0x1668
assert backend_size and int(backend_size[1],16) == expected_backend_bytes
# These are exact original address aliases for eventual backend builds. The
# annotation itself is deliberately never linked into a runtime kernel.
binding_output=OUT/('interface-original-bindings.S' if (OUT/'original-bindings.o').exists() else 'original-bindings.S')
binding_output.write_text(''.join(f'.globl {name}\n.set {name}, {va:#x}\n' for name, va in sorted(bindings.items())))
report = dict(scope='Static actual compiler ABI; no display publication or runtime',
    target_os=contract['target_os'], candidate_sha256=contract['candidate_sha256'],
    original_family_text_sha256=contract['original_family_text_sha256'],
    checked_slots=338, compiled_class_bytes=0x1660, original_class_bytes=0x1660,
    inherited_native_slots=inherited, original_method_slots=338-len(owned)-inherited,
    annotation_owned_slots=owned, abstract_leaves=contract['abstract_slots'],
    backend_owned_slots=backend_owned, backend_compiled_class_bytes=expected_backend_bytes,
    backend_checked_slots=338, backend_compiled_object_sha256=hashlib.sha256(backend).hexdigest(),
    gop_mapping_source_compiled=True, presentation_implemented=False,
    bindings={name:hex(address) for name,address in sorted(bindings.items())},
    compiled_object_sha256=hashlib.sha256(obj).hexdigest(),
    audit_sha256=contract['audit_sha256'], compiler_receipt_sha256=hashlib.sha256((OUT/'compile-receipt.json').read_bytes()).hexdigest(),
    linked=False, executed=False, unknown_prototypes_qualified=False,
    backend_implemented=False, runtime_verified=False, desktop_verified=False,
    device_commands_executed=False)
(OUT/'interface-compiler-audit.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k != 'bindings'}, indent=2))
