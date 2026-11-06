"""Recover and audit the native PAN copyio object with an ARMv8.1 target."""
from pathlib import Path
import json
import subprocess

root = Path('/home/odin/unixnu-odin-build')
out = root/'evidence/odin-native-pan-u10'
out.mkdir(exist_ok=True)
record = json.loads((root/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/copyio.o.json').read_text().strip().rstrip(','))
arguments = record['arguments']
assert any(arg in ('-DXNU_NATIVE_PAN=1', 'XNU_NATIVE_PAN=1') for arg in arguments)
arguments += ['-march=armv8.1-a']
preprocess = []
skip = False
for arg in arguments:
    if skip:
        skip = False
        continue
    if arg in ('-o', '-MF', '-MJ'):
        skip = True
    elif arg not in ('-c', '-MD', '-MP'):
        preprocess.append(arg)
preprocess += ['-E', '-dM']
result = subprocess.run(preprocess, cwd=record['directory'], capture_output=True, text=True, check=True)
(out/'copyio-macros.txt').write_text(result.stdout)
assert '#define __ARM_PAN_AVAILABLE__ 1' in result.stdout
assert '#define XNU_NATIVE_PAN 1' in result.stdout
subprocess.run(arguments, cwd=record['directory'], check=True)
(out/'compile.json').write_text(json.dumps({'directory':record['directory'], 'arguments':arguments,
    'reason':'Cortex-A76/MIX4 support PAN; the compiler must also target ARMv8.1+',
    'runtime_verified':False, 'device_commands_executed':False}, indent=2)+'\n')
print('copyio macro contract and real ARMv8.1 PAN compilation verified')
