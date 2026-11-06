"""Linux annotation build of pinned public storage source; never linked."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile

root = Path('/home/odin/unixnu-odin-build')
up = root / 'upstream'
out = root / 'evidence/odin-storage-abi-u12'
out.mkdir(exist_ok=True)
archive = root / 'IOStorageFamily-315.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'ec28dca0231ef58c7d347153cf572c60440bf25e198095af02a19bf0167b8438'
source = out / 'IOStorageFamily-e45fbe30a7879e0b16e26dddb78538f1b00e0bff'
if not source.exists():
    with tarfile.open(archive) as stream:
        stream.extractall(out, filter='data')
include = up / 'build/storage-abi/include'
headers = include / 'IOKit/storage'
headers.mkdir(parents=True, exist_ok=True)
for path in source.glob('*.h'):
    shutil.copyfile(path, headers / path.name)
conditions = Path('/home/odin/xnu-work/project/xnu-deps/MacOSX13.3.sdk/usr/include/TargetConditionals.h')
shutil.copyfile(conditions, include / 'TargetConditionals.h')
# This macOS SDK header defaults to OSX even for --target=arm64-apple-ios.
# Select the actual iOS platform after its include guard; do not change the
# public class declaration or pretend the desktop dispatch ABI is iOS.
target = out / 'odin-ios-target.h'
target.write_text('''#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wmacro-redefined"
#include <TargetConditionals.h>
#pragma clang diagnostic pop
#undef TARGET_OS_OSX
#undef TARGET_OS_IPHONE
#undef TARGET_OS_IOS
#undef TARGET_OS_EMBEDDED
#define TARGET_OS_OSX 0
#define TARGET_OS_IPHONE 1
#define TARGET_OS_IOS 1
#define TARGET_OS_EMBEDDED 1
''')
record = json.loads((up / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
command = []
args = record['arguments']
i = 0
while i < len(args):
    value = args[i]
    if value == record['file']:
        command.append(str(source / 'IOBlockStorageDevice.cpp'))
    elif value == '-o':
        command += ['-o', str(out / 'IOBlockStorageDevice-reference.o')]
        i += 1
    elif value in ('-MF', '-MJ'):
        i += 1
    elif value == '-Xclang' and args[i + 1].startswith('-W'):
        i += 1
    elif not value.startswith(('-W', '--ld-path=')) and value not in ('-MD', '-MP', '-w'):
        command.append(value)
    i += 1
command += ['-I', str(include), '-I', str(up / '.cache/xnu-work/osfmk'), '-include', str(target),
            '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
            '-Wno-deprecated-declarations', '-Wno-c99-designator', '-Wno-reorder-init-list',
            '-Wno-deprecated-enum-enum-conversion', '-Wno-missing-field-initializers']
(out / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
r = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True)
(out / 'compile.log').write_text(r.stdout + r.stderr)
if r.returncode:
    raise SystemExit((r.stdout + r.stderr)[-5000:])
dwarf = subprocess.check_output(['llvm-dwarfdump', '--name=IOBlockStorageDevice', '--show-children', out / 'IOBlockStorageDevice-reference.o'], text=True)
(out / 'class-dwarf.txt').write_text(dwarf)
(out / 'provenance.json').write_text(json.dumps({
    'revision': 'e45fbe30a7879e0b16e26dddb78538f1b00e0bff',
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'reference_executed_or_linked': False,
    'headers': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(headers.glob('*.h'))},
    'target_conditions_sha256': hashlib.sha256(conditions.read_bytes()).hexdigest(),
    'ios_selection_header_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
}, indent=2) + '\n')
print('Public storage reference compiled; original iOS16.5 ABI comparison pending')
