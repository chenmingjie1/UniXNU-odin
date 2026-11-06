"""Find original 20F66 HID class tables and emit static edge-ABI evidence.

Does not write to a device or authorize using another release's virtual slots.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import subprocess

D = Path(__file__).resolve().parents[1]
ROOT = D.parent.parent
sys.path.insert(0, str(ROOT / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np


def main():
    directory = D / 'build/hid-edge-ios16'
    directory.mkdir(exist_ok=True)
    source = D / 'build/ios16-prelink-u12match'
    blob = (source / 'kernel.prelinked.experimental.macho').read_bytes()
    plan = json.loads((source / 'prelink-emission-report.json').read_text())
    assert hashlib.sha256(blob).hexdigest() == plan['candidate_sha256']
    image = np.macho(blob)
    exports = np.exports(blob, image)
    names = {n: a for a, ns in exports.items() for n in ns}
    segments = {e['segment']: e for e in plan['extents']
                if e['module'] == 'com.apple.iokit.IOHIDFamily'}

    def read(address, size):
        at = np.backed_offset(image['segments'], address, size, len(blob))
        return blob[at:at + size]

    def pair(pc, a, b):
        if a & 0x9f000000 != 0x90000000 or b & 0xffc00000 != 0x91000000:
            return None
        if a & 31 != (b >> 5) & 31:
            return None
        imm = ((a >> 5 & 0x7ffff) << 2) | (a >> 29 & 3)
        if imm & 0x100000:
            imm -= 0x200000
        return (pc & ~4095) + (imm << 12) + (b >> 10 & 4095), b & 31

    text, const, strings = (segments[n] for n in ('__TEXT_EXEC', '__DATA_CONST', '__TEXT'))
    code, data, string_data = (read(s['va'], s['size']) for s in (text, const, strings))
    assert hashlib.sha256(code).hexdigest() == plan['original_executable_sha256']['com.apple.iokit.IOHIDFamily']
    prefix = struct.pack('<5Q', *(names[n] for n in (
        '__ZNK8OSObject7releaseEi', '__ZNK8OSObject14getRetainCountEv',
        '__ZNK8OSObject6retainEv', '__ZNK8OSObject7releaseEv', '__ZNK8OSObject9serializeEP11OSSerialize')))
    tables = []
    offset = data.find(prefix)
    while offset >= 0:
        start = offset - 32
        if start >= 0 and start % 8 == 0 and data[start:start + 16] == bytes(16):
            methods = []
            at = start + 16
            while at + 8 <= len(data):
                address, = struct.unpack_from('<Q', data, at)
                if not address or not (text['va'] <= address < text['va'] + text['size'] or address in exports):
                    break
                methods.append(address)
                at += 8
            if len(methods) >= 18:
                getter = read(methods[7], 24)
                meta = None
                for delta in (0, 8):
                    p = pair(methods[7] + delta, *struct.unpack_from('<II', getter, delta))
                    if p and p[1] == 0 and struct.unpack_from('<I', getter, delta + 8)[0] == 0xd65f03c0:
                        meta = p[0]
                tables.append(dict(vptr=hex(const['va'] + start + 16), entries=len(methods),
                                   metaclass=hex(meta) if meta else None,
                                   methods=[hex(a) for a in methods]))
        offset = data.find(prefix, offset + 1)
    wanted = {}
    for name in ('IOHIDEvent', 'IOHIDEventService', 'IOHIDEventDriver'):
        needle = b'\0' + name.encode() + b'\0'
        offsets = [i + 1 for i in range(len(string_data)) if string_data.startswith(needle, i)]
        assert len(offsets) == 1, (name, offsets)
        wanted[strings['va'] + offsets[0]] = name
    references = []
    assembly = ['.text']
    for off in range(0, len(code) - 8, 4):
        p = pair(text['va'] + off, *struct.unpack_from('<II', code, off))
        if p and p[0] in wanted:
            pc = text['va'] + off
            references.append(dict(name=wanted[p[0]], pc=hex(pc), register=p[1]))
            assembly += [f'// {wanted[p[0]]} {pc:#x}', f'.org {off - 24}']
            assembly += [f'.inst 0x{word:08x}' for word, in struct.iter_unpack('<I', code[off - 24:off + 80])]
    # Separate per-window objects avoid overlapping windows in the diagnostic output.
    tool = ROOT / 'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
    for ref in references:
        pc = int(ref['pc'], 16)
        stem = directory / (ref['name'] + '-' + ref['pc'])
        raw = read(pc - 24, 104)
        stem.with_suffix('.S').write_text('.text\n' + ''.join(f'.inst 0x{w:08x}\n' for w, in struct.iter_unpack('<I', raw)))
        subprocess.run([str(tool / 'clang.exe'), '--target=aarch64-none-elf', '-c', str(stem.with_suffix('.S')), '-o', str(stem.with_suffix('.o'))], check=True)
        result = subprocess.run([str(tool / 'llvm-objdump.exe'), '-d', '--adjust-vma=' + hex(pc - 24), str(stem.with_suffix('.o'))], capture_output=True, text=True, check=True)
        stem.with_suffix('.txt').write_text(result.stdout)
    result = dict(target='iOS16.5/20F66', original_sha256=plan['original_sha256'],
                  candidate_sha256=plan['candidate_sha256'], family_text_sha256=hashlib.sha256(code).hexdigest(),
                  references=references, tables=tables, runtime_qualified=False)
    (directory / 'discovery.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(references=references, table_count=len(tables), output=str(directory))))


if __name__ == '__main__':
    main()
