"""Read-only LLVM disassembly of a bounded original display-method window."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / 'work/UniXNU-odin'
sys.path.insert(0, str(ROOT / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--address', type=lambda x: int(x, 0))
p.add_argument('--slot', type=int)
p.add_argument('--class-name', default='IOMobileFramebufferLegacy')
p.add_argument('--bytes', type=lambda x: int(x, 0), default=512)
p.add_argument('--output', required=True)
a = p.parse_args()
assert (a.address is None) != (a.slot is None)
assert 4 <= a.bytes <= 16384 and a.bytes % 4 == 0
record = json.loads((DEV / 'build/display-analysis-ios16/dispatch-discovery.json').read_text())
legacy = next(t for t in record['dispatch_candidates'] if t.get('name') == a.class_name)
address = a.address if a.address is not None else int(legacy['methods'][a.slot]['address'], 16)
kernel = DEV / 'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho'
blob = kernel.read_bytes()
image = np.macho(blob)
at = np.backed_offset(image['segments'], address, a.bytes, len(blob))
command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'UserKnownHostsFile='+str(ROOT/'outputs/MIX4-odin-porting/kernel-touch-init-integrated-20261101/guest-known-hosts'),
    '-i', str(ROOT/'work/odin-portable-linux/guest-ssh-key'), '-p', '18474', 'odin@127.0.0.1',
    'llvm-mc --disassemble --triple=aarch64']
result = subprocess.run(command, input=' '.join(hex(x) for x in blob[at:at+a.bytes])+'\n',
                        capture_output=True, text=True, timeout=30, check=True)
assert not result.stderr, result.stderr
instructions = [line.strip() for line in result.stdout.splitlines() if line.strip() and line.strip() != '.text']
assert len(instructions) == a.bytes//4, (len(instructions), a.bytes//4)
text = '\n'.join(f'{address+i*4:#x}: {line}' for i, line in enumerate(instructions))+'\n'
output = DEV/'build/display-analysis-ios16'/a.output
assert output.resolve().is_relative_to((DEV/'build/display-analysis-ios16').resolve())
output.write_text(text)
print(text)
