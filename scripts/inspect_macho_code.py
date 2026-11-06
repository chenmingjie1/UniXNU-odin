"""Disassemble a file-backed Mach-O VA range, including appended prelink code."""
from pathlib import Path
import argparse
import hashlib
import struct
import subprocess

root = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
parser.add_argument('address', type=lambda value: int(value, 0))
parser.add_argument('size', type=lambda value: int(value, 0))
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert 0 < args.size <= 65536 and args.size % 4 == args.address % 4 == 0
data = args.image.read_bytes()
assert data[:4] == bytes.fromhex('cffaedfe')
pos = 32
raw = None
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    command, size = struct.unpack_from('<II', data, pos)
    if command == 25:
        name, va, vs, offset, backed = struct.unpack_from('<16s4Q', data, pos+8)
        if va <= args.address and args.address + args.size <= va + backed:
            assert raw is None
            raw = data[offset + args.address-va:offset + args.address-va + args.size]
    pos += size
assert raw is not None, 'Range is not backed by one segment'
args.output.mkdir(parents=True, exist_ok=True)
source, obj = args.output/'range.S', args.output/'range.o'
source.write_text('.text\n.globl inspected_range\ninspected_range:\n' +
    ''.join(f'.inst 0x{value:08x}\n' for value, in struct.iter_unpack('<I', raw)))
tools = root/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
subprocess.run([str(tools/'clang.exe'), '--target=aarch64-none-elf', '-c', str(source), '-o', str(obj)], check=True)
result = subprocess.run([str(tools/'llvm-objdump.exe'), '-d', str(obj)], check=True, capture_output=True, text=True)
report = f'Input SHA256: {hashlib.sha256(data).hexdigest()}\nOriginal VA: {args.address:#x}\nOffsets below are relative to that VA.\n' + result.stdout
(args.output/'disassembly.txt').write_text(report)
print(report)
