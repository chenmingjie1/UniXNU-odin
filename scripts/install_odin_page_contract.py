"""Repair the board's 4K page policy despite Apple compatibility headers.

The SDK's commpage header brings in apple_arm64_common.h even on BCM2837.
Do not infer the physical board from that incidental macro definition.
"""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess

ROOT = Path('/home/odin/unixnu-odin-build')
TREE = ROOT/'upstream/.cache/xnu-work'
OUT = ROOT/'evidence/odin-page-contract-u09'
OUT.mkdir(exist_ok=False)
record = json.loads((ROOT/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/arm_init.o.json').read_text().strip().rstrip(','))
args = record['arguments']
assert 'ARM64_BOARD_CONFIG_BCM2837' in args
command = []
skip = False
for arg in args:
    if skip:
        skip = False
        continue
    if arg == '-o':
        skip = True
        continue
    if arg != '-c':
        command.append(arg)
command += ['-E', '-dM']
result = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True, check=True)
(OUT/'arm-init-macros.txt').write_text(result.stdout)
macros = dict(line[8:].split(' ', 1) if ' ' in line[8:] else (line[8:], '')
              for line in result.stdout.splitlines() if line.startswith('#define '))
assert macros['ARM64_BOARD_CONFIG_BCM2837'] == '1'
assert macros['APPLE_ARM64_ARCH_FAMILY'] == '1'
assert macros.get('__ARM_16K_PG__', '0') == '0'
old = '#if !defined(APPLE_ARM64_ARCH_FAMILY) && !__ARM_16K_PG__'
new = '#if (defined(ARM64_BOARD_CONFIG_BCM2837) || !defined(APPLE_ARM64_ARCH_FAMILY)) && !__ARM_16K_PG__'
paths = {'osfmk/arm/arm_init.c': 2, 'bsd/kern/mach_loader.c': 1,
         'osfmk/arm/commpage/commpage.c': 1, 'osfmk/vm/vm_shared_region.c': 1}
patch = ''
files = []
for name, expected in paths.items():
    path = TREE/name
    before = path.read_text()
    assert before.count(old) == expected, name
    after = before.replace(old, new)
    backup = OUT/name
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(before)
    path.write_text(after)
    patch += ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/'+name, tofile='b/'+name))
    files.append({'path': name, 'source_sha256': hashlib.sha256(after.encode()).hexdigest()})
(OUT/'odin-page-contract.patch').write_text(patch)
(OUT/'verification.json').write_text(json.dumps({'files': files,
    'compiler_macro_evidence': 'arm-init-macros.txt',
    'reason': 'Apple compatibility headers define APPLE_ARM64_ARCH_FAMILY on the native BCM2837 build',
    'hardware_page_shift': 12, 'old_large_memory_advertised_page_shift': 14,
    'runtime_verified': False, 'device_commands_executed': False}, indent=2)+'\n')
print('Board-specific 4K page contract installed; rebuild and large-root replay required')
