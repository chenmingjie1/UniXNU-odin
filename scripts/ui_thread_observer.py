"""Read-only integration of pinned UniXNU QEMU thread observation.

The caller owns the sole GDB/QMP connection. No second debugger is attached.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import xml.etree.ElementTree as ET

DEV = Path(__file__).resolve().parents[1]
UPSTREAM = DEV / 'research/github-display-20261104/UniXNU--UniXNU/source/UniXNU-82b847c4ac3f68a57024b3082ffa3a03442defd9/scripts/qemu-entry'


class Observer:
    def __init__(self, packet, plan):
        self.packet, self.plan = packet, plan
        self.layout = plan['process_layout']
        self.registers = {}

        def feature(name):
            offset, text = 0, ''
            while offset < 1024 * 1024:
                chunk = packet(f'qXfer:features:read:{name}:{offset:x},1000')
                if not chunk or chunk[0] not in 'ml':
                    raise ValueError('QEMU register feature unavailable: ' + name)
                text += chunk[1:]
                offset += len(chunk) - 1
                if chunk[0] == 'l':
                    if 'xi:include' in text and 'xmlns:xi=' not in text:
                        text = text.replace('<target', '<target xmlns:xi="http://www.w3.org/2001/XInclude"', 1)
                    return ET.fromstring(text)
            raise ValueError('Oversized register description')

        for include in feature('target.xml').findall('{http://www.w3.org/2001/XInclude}include'):
            for register in feature(include.attrib['href']).findall('reg'):
                if register.attrib['name'] in ('TPIDR_EL1', 'TCR_EL1'):
                    self.registers[register.attrib['name']] = int(register.attrib['regnum'])
        assert len(self.registers) == 2
        source = UPSTREAM / 'thread_snapshot.py'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == plan['upstream_files'][source.name]
        spec = importlib.util.spec_from_file_location('qualified_upstream_thread_snapshot', source)
        self.upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.upstream)

    def read(self, address, length, user=False):
        lower, upper = (0x1000, 0x8000000000) if user else (0xfffffff000000000, 1 << 64)
        if not lower <= address < upper - length or not 0 < length <= 304:
            raise ValueError('Invalid bounded observer read')
        raw = self.packet(f'm{address:x},{length:x}')
        if raw.startswith('E') or len(raw) != length * 2:
            raise ValueError('Observer memory is unavailable')
        return bytes.fromhex(raw)

    def word(self, address, length=8):
        return int.from_bytes(self.read(address, length), 'little')

    def register(self, name):
        raw = self.packet(f'p{self.registers[name]:x}')
        assert len(raw) == 16 and not raw.startswith('E')
        return int.from_bytes(bytes.fromhex(raw), 'little')

    def identity(self):
        l = self.layout
        thread = self.register('TPIDR_EL1')
        ro = self.word(thread + l['thread_ro'])
        assert self.word(ro + l['ro_owner']) == thread
        proc = self.word(ro + l['ro_proc'])
        task = self.word(ro + l['ro_task'])
        region = self.word(task + l['task_region'])
        return dict(thread=hex(thread), proc=hex(proc), task=hex(task),
            pid=self.word(proc + l['pid'], 4),
            name=self.read(proc + l['comm'], 17).split(b'\0')[0].decode('utf8', 'replace'),
            cache_slide=self.word(region + l['region_slide'], 4) if region else None)

    def fatal(self, address):
        row = dict(saved_state_address=hex(address), read_only=True)
        try:
            state = self.read(address, 288)
            assert struct.unpack_from('<2I', state) == (21, 72)
            regs = struct.unpack_from('<33Q', state, 8)
            row.update(process=self.identity(),
                registers={**{f'X{i:02}': hex(v) for i, v in enumerate(regs[:29])},
                    'FP': hex(regs[29]), 'LR': hex(regs[30]), 'SP': hex(regs[31]), 'PC': hex(regs[32])},
                cpsr=hex(struct.unpack_from('<I', state, 272)[0]), strings={}, frames=[])
            if int(row['cpsr'], 16) & 31:
                return row
            for name, va in [('X00', regs[0]), ('X19', regs[19]), ('SP', regs[31]), ('SP16', regs[31] + 16)]:
                try:
                    data = self.read(va, min(256, 4096 - (va & 4095)), user=True)
                    row['strings'][name] = dict(address=hex(va), hex=data.hex(),
                        text=data.split(b'\0')[0].decode('utf8', 'replace'))
                except ValueError:
                    pass
            fp, sp = regs[29], regs[31]
            for _ in range(24):
                if not fp or fp & 15 or not sp <= fp < sp + 65536:
                    break
                next_fp, lr = struct.unpack('<2Q', self.read(fp, 16, user=True))
                row['frames'].append(dict(fp=hex(fp), lr=hex(lr)))
                if next_fp <= fp:
                    break
                fp = next_fp
        except (ValueError, AssertionError) as error:
            row['error'] = str(error)
        return row

    def capture(self):
        rows, seen = [], set()
        l = self.layout
        node = self.word(self.plan['allproc'])
        while node and node not in seen and len(rows) < 512:
            seen.add(node)
            rows.append(dict(address=hex(node), pid=self.word(node + l['pid'], 4),
                name=self.read(node + l['comm'], 17).split(b'\0')[0].decode('utf8', 'replace'),
                state=self.word(node + l['stat'], 1)))
            node = self.word(node + l['list'])
        return dict(process_list=rows, list_complete=node == 0,
            ui_thread_snapshots=self.upstream.capture(self.packet, rows, self.plan,
                {'TCR_EL1': hex(self.register('TCR_EL1'))}))
