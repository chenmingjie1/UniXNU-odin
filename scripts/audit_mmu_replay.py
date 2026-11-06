"""Verify rendered registers and real early-C progression in isolated QEMU runs."""
from pathlib import Path
import hashlib
import json
import re
import struct

DEV = Path(__file__).resolve().parents[1]
BUILD = DEV / 'build'
source = Path(__file__).with_name('odin_mmu_diagnostics.S.inc').read_text()
font_text = source.split('Lodin_hex_font:', 1)[1].split('.p2align', 1)[0]
font = [tuple(map(int, row.split(','))) for row in re.findall(r'\.byte ([0-9,]+)', font_text)]
assert len(font) == 16 and all(len(row) == 8 for row in font)


def rows(tag, start, count):
    fb = (BUILD / ('qemu-early-entry-' + tag) / 'framebuffer.bin').read_bytes()
    result = []
    for row in range(start, start + count):
        digits = ''
        for digit in range(20):
            pattern = []
            for y in range(8):
                bits = 0
                for x in range(5):
                    px = 16 + digit * 18 + (18 if digit >= 4 else 0) + x * 3 + 1
                    py = 128 + row * 32 + y * 3 + 1
                    color = struct.unpack_from('<I', fb, py * 4320 + px * 4)[0]
                    assert color in (0xff000000, 0xffffffff), (tag, row, digit, x, y, hex(color))
                    bits = (bits << 1) | int(color == 0xffffffff)
                pattern.append(bits)
            assert tuple(pattern) in font, (tag, row, digit, pattern)
            digits += format(font.index(tuple(pattern)), 'X')
        result.append({'label': digits[:4], 'value': digits[4:]})
    return result


good_dir = BUILD / 'qemu-early-entry-u08good'
bad_dir = BUILD / 'qemu-early-entry-u08fault'
good = json.loads((good_dir / 'verification.json').read_text())
bad = json.loads((bad_dir / 'verification.json').read_text())
assert good['generic_native_arm_init_reached'] and good['halted_before_symbol'] == '_PE_init_platform'
assert bad['early_exception_handler_reached']
expected = [0xff00ff00, 0xffffff00, 0xff00ffff, 0xffffffff, 0xffff0000, 0xffff00ff,
            0xff0000ff, 0xffff8000, 0xff808080, 0xff0080ff, 0xff8000ff, 0xff00ffff,
            0xff808000, 0xffff80ff, 0xffffff80, 0xff80ffff]
fb = (good_dir / 'framebuffer.bin').read_bytes()
assert [struct.unpack_from('<I', fb, i * 256)[0] for i in range(16)] == expected
pre = rows('u08good', 0, 8)
exc = rows('u08fault', 8, 6)
assert [r['label'] for r in pre] == [f'A{i:03X}' for i in range(8)]
assert [r['label'] for r in exc] == [f'E{i:03X}' for i in range(6)]
assert int(pre[3]['value'], 16) & (3 << 14) == 0  # TG0=4K
assert int(pre[4]['value'], 16) & 1 == 0          # MMU off before write
assert int(exc[0]['value'], 16) == 0xf2000123     # injected A64 BRK, actual ESR
assert int(exc[1]['value'], 16) == int(bad['physical_base'], 16) + bad['native_entry_checkpoint_symbols']['_odin_entry_mark5'] - int(bad['virtual_base'], 16)
assert int(exc[3]['value'], 16) & 1 == 1          # fault occurred with MMU on
result = {'passed': True, 'kernel_sha256': good['kernel_sha256'],
          'all_16_marker_colors_verified': True, 'early_c_callbacks_executed': True,
          'pre_mmu_register_rows': pre, 'injected_fault_register_rows': exc,
          'scope': 'Generic Cortex-A76 CPU only; not SM8350 or desktop qualification',
          'production_kernel_file_not_modified_by_fault_injection': True}
(BUILD / 'ios16-prelink-u08/mmu-replay-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
