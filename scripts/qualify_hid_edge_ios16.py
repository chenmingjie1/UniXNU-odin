"""Bind the narrowly measured arm64 20F66 edge-event interface, not a generic HID ABI."""
from pathlib import Path
import hashlib
import json
import struct
import sys

D = Path(__file__).resolve().parents[1]
ROOT = D.parent.parent
sys.path.insert(0, str(ROOT / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np


def main():
    folder = D / 'build/hid-edge-ios16'
    discovery = json.loads((folder / 'discovery.json').read_text())
    assert discovery['target'] == 'iOS16.5/20F66'
    assert discovery['original_sha256'] == 'e6fa75598f47b5a9460a60913e2ac8e4cd6cd60eb475bb31da65b68ffbcfdad5'
    assert discovery['family_text_sha256'] == 'f50ee9543f8a27cb87eebdcc868559b4c38cdc4f76a11df1036b36d13584054d'
    b = (D / 'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho').read_bytes()
    assert hashlib.sha256(b).hexdigest() == discovery['candidate_sha256']
    image = np.macho(b)

    def words(address, count):
        at = np.backed_offset(image['segments'], address, count * 4, len(b))
        return struct.unpack_from('<' + str(count) + 'I', b, at)

    def table(address, entries, meta):
        found = [t for t in discovery['tables'] if t['vptr'] == hex(address)]
        assert len(found) == 1
        t = found[0]
        assert t['entries'] == entries and t['metaclass'] == hex(meta)
        return t

    driver = table(0xfffffff005cc0130, 219, 0xfffffff006a0dc30)
    event = table(0xfffffff005cc09d8, 37, 0xfffffff006a0dc58)
    # Actual original class constructor references these exact vptrs. Class
    # names/meta registrations and their original sizes were disassembled too.
    assert words(0xfffffff004741014, 3) == (0xf000abe8, 0x9104c108, 0xf9000008)
    assert words(0xfffffff00474b440, 3) == (0xb000aba8, 0x91276108, 0xf9000008)
    checks = {
        'getType': (18, 0xfffffff00474d208, (0xf9400808, 0xb9400500, 0xd65f03c0)),
        'getIntegerValue': (23, 0xfffffff00474d230, (0xa9be4ff4, 0xa9017bfd, 0x910043fd)),
        'setIntegerValue': (24, 0xfffffff00474f09c, (0xa9bd57f6, 0xa9014ff4, 0xa9027bfd)),
        'getFixedValue': (25, 0xfffffff00474e620, (0xa9be4ff4, 0xa9017bfd, 0x910043fd)),
        'appendChild': (15, 0xfffffff00474d158, (0xd100c3ff, 0xa9014ff4, 0xa9027bfd)),
    }
    records = {}
    for name, (slot, address, prefix) in checks.items():
        assert int(event['methods'][slot], 16) == address
        assert words(address, len(prefix)) == prefix
        records[name] = dict(slot=slot, address=hex(address))
    # appendChild reads and writes children at +0x18 in two independent paths.
    assert words(0xfffffff00474d17c, 1) == (0xf9400c00,)
    assert words(0xfffffff00474d1c8, 1) == (0xf9000e60,)
    assert int(driver['methods'][198], 16) == 0xfffffff00474aff8
    # Original override calls super::dispatchEvent with the same self/event/options.
    # The whole family executable hash above binds this inspected body, including
    # its tail call; no slot is inferred merely from a name or another OS version.
    assert words(0xfffffff00474aff8, 3) == (0xa9bc5ff8, 0xa90157f6, 0xa9024ff4)
    output = dict(target='iOS16.5/20F66', family_text_sha256=discovery['family_text_sha256'],
                  driver_vptr=driver['vptr'], driver_slots=219, dispatch_slot=198,
                  event_vptr=event['vptr'], event_slots=37, children_offset=24,
                  event_methods=records, runtime_qualified=False,
                  limits='Static original-family ABI qualification only; physical Home gesture remains untested')
    (folder / 'contract.json').write_text(json.dumps(output, indent=2) + '\n')
    (folder / 'bindings.S').write_text(
        '.globl _odin_edge_driver_table\n.set _odin_edge_driver_table, ' + driver['vptr'] + '\n' +
        '.globl _odin_edge_event_table\n.set _odin_edge_event_table, ' + event['vptr'] + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
