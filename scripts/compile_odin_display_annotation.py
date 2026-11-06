"""VM-side compiler check of the 16.5 display ABI; never link or execute it."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path('/home/odin/unixnu-odin-build')
up = root/'upstream'
out = root/'evidence/odin-display-abi-u14'
out.mkdir(exist_ok=True)
source = out/'OdinDisplayABIAnnotation.cpp'
contract = json.loads((out/'interface-contract.json').read_text())
assert contract['expected_entries'] == 338 and contract['instance_bytes'] == 0x1660
target = root/'evidence/odin-storage-abi-u12/odin-ios-target.h'
assert target.exists()
record = json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
command = []
args = record['arguments']
i = 0
while i < len(args):
    value = args[i]
    if value == record['file']:
        command.append(str(source))
    elif value == '-o':
        command += ['-o', str(out/'OdinDisplayABIAnnotation.o')]
        i += 1
    elif value in ('-MF', '-MJ'):
        i += 1
    elif value == '-Xclang' and args[i+1].startswith('-W'):
        i += 1
    elif not value.startswith(('-W', '--ld-path=')) and value not in ('-MD', '-MP', '-w'):
        command.append(value)
    i += 1
command += ['-I', str(out), '-I', str(up/'build/storage-abi/include'),
    '-I', str(up/'.cache/xnu-work/osfmk'), '-include', str(target), '-g',
    '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
    '-Wno-deprecated-declarations', '-Wno-c99-designator', '-Wno-reorder-init-list',
    '-Wno-deprecated-enum-enum-conversion', '-Wno-missing-field-initializers']
(out/'compile-command.json').write_text(json.dumps(command, indent=2)+'\n')
r = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True)
(out/'compile.log').write_text(r.stdout+r.stderr)
if r.returncode:
    raise SystemExit((r.stdout+r.stderr)[-6000:])
backend_command = [str(out/'OdinLegacyGOPDisplay.cpp') if value == str(source)
                   else str(out/'OdinLegacyGOPDisplay.o') if value == str(out/'OdinDisplayABIAnnotation.o')
                   else value for value in command]
(out/'backend-compile-command.json').write_text(json.dumps(backend_command, indent=2)+'\n')
r = subprocess.run(backend_command, cwd=record['directory'], capture_output=True, text=True)
(out/'backend-compile.log').write_text(r.stdout+r.stderr)
if r.returncode:
    raise SystemExit((r.stdout+r.stderr)[-6000:])
dwarf = subprocess.check_output(['llvm-dwarfdump', '--name=OdinDisplayABIAnnotation',
    '--name=IOMobileFramebufferLegacy', '--show-children', out/'OdinDisplayABIAnnotation.o'], text=True)
(out/'class-dwarf.txt').write_text(dwarf)
backend_dwarf = subprocess.check_output(['llvm-dwarfdump', '--name=OdinLegacyGOPDisplay',
    '--show-children', out/'OdinLegacyGOPDisplay.o'], text=True)
(out/'backend-class-dwarf.txt').write_text(backend_dwarf)
(out/'compile-receipt.json').write_text(json.dumps(dict(
    scope='Compiler ABI annotation; never linked or executed',
    target_os=contract['target_os'],
    files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        source, out/'OriginalLegacyFramebufferABI.h', out/'interface-contract.json',
        out/'OdinDisplayABIAnnotation.o', out/'class-dwarf.txt', out/'compile-command.json',
        out/'OdinLegacyGOPDisplay.cpp', out/'OdinLegacyGOPDisplay.o', out/'backend-class-dwarf.txt',
        out/'backend-compile-command.json')},
    original_source_recipe_sha256=hashlib.sha256((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_bytes()).hexdigest(),
    compiled=True, linked=False, executed=False, runtime_verified=False,
    desktop_verified=False, device_commands_executed=False), indent=2)+'\n')
print('PASS: iOS16 display annotation and GOP mapping backend compiled with -Wall -Wextra -Werror; neither linked nor executed')
