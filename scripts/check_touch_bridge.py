"""Host execution plus freestanding ARM64 compile; no phone I/O."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess

DEVICE = Path(__file__).resolve().parent.parent
WORKSPACE = DEVICE.parent.parent
SOURCE = DEVICE / 'package/OdinStTouch'
OUT = DEVICE / 'build/host-touch'
OUT.mkdir(parents=True, exist_ok=True)
LOCAL_CLANG = WORKSPACE / 'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin/clang.exe'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cc', default=shutil.which('gcc') or shutil.which('clang'))
parser.add_argument('--clang', default=str(LOCAL_CLANG) if LOCAL_CLANG.is_file() else shutil.which('clang'))
args = parser.parse_args()
CC, CLANG = args.cc, args.clang
if not CC or not CLANG:
    raise SystemExit('Need host C compiler and cross-capable clang; specify --cc and --clang')

commands = [
    [CC, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(SOURCE),
     str(SOURCE / 'OdinStHidBridge.c'), str(DEVICE / 'tests/touch_bridge_test.c'),
     '-o', str(OUT / 'touch_bridge_test.exe')],
    [str(CLANG), '--target=aarch64-none-elf', '-ffreestanding', '-std=c11', '-O2',
     '-Wall', '-Wextra', '-Werror', '-I', str(SOURCE), '-c',
     str(SOURCE / 'OdinStHidBridge.c'), '-o', str(OUT / 'OdinStHidBridge-aarch64.o')],
    [str(CLANG), '--target=arm64-apple-darwin', '-ffreestanding', '-std=c11', '-O2',
     '-Wall', '-Wextra', '-Werror', '-I', str(SOURCE), '-c',
     str(SOURCE / 'OdinStHidBridge.c'), '-o', str(OUT / 'OdinStHidBridge-arm64-macho.o')],
]
for command in commands:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
result = subprocess.run([str(OUT / 'touch_bridge_test.exe')], capture_output=True, text=True)
if result.returncode:
    raise SystemExit(result.stdout + result.stderr)
record = json.loads(result.stdout)
record.update(scope='ST wire protocol + HID report adapter only; not IOHIDDevice, kernel link or hardware qualification',
              device_io=False, full_kernel_linked=False, boot_image_created=False,
              commands=commands,
              sources={str(p.relative_to(DEVICE)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [*SOURCE.glob('*'), DEVICE / 'tests/touch_bridge_test.c'] if p.is_file()},
              objects={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.o')})
(OUT / 'verification.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record, indent=2))
