"""Audit the exact original iOS16 AMFI AON imports, then build the BSD bridge."""
from pathlib import Path
import hashlib, json, struct, subprocess, sys, tarfile

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
OUT = DEV/'build/pmgr-u73'
OUT.mkdir(exist_ok=True)
assert not (OUT/'native-real-iig.macho').exists(), 'Preserve completed candidate'
sys.path.insert(0, str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
sys.path.insert(0, str(DEV/'scripts'))
from build_odin_display_owner import SSH, SCP

parent = DEV/'build/virtual-timer-u72/kernel.prelinked.experimental.macho'
blob = parent.read_bytes()
assert hashlib.sha256(blob).hexdigest() == '225a8b4d53cf4f9ae6e156dc5ac308861d2100073a1a8e84cb279db954327950'
image = np.macho(blob)
original = (DEV/'build/ios16-prelink/kernelcache.decompressed').read_bytes()
original_image = np.macho(original)
def read(data, parsed, address, length):
    off = np.backed_offset(parsed['segments'], address, length, len(data))
    return data[off:off+length]
proof = {}
for name, stub, expected in [
    ('readAon', 0xfffffff00471ae10,
     [0xf9404400, 0xb4000080, 0xf9400008, 0xf944dd01, 0xd61f0020, 0x12800000, 0xd65f03c0]),
    ('writeAon', 0xfffffff00471ae1c,
     [0xf9404400, 0xb4000080, 0xf9400008, 0xf944e102, 0xd61f0040, 0xd65f03c0])]:
    adrp, ldr, branch = struct.unpack('<3I', read(blob, image, stub, 12))
    assert adrp & 0x9f00001f == 0x90000010 and ldr & 0xffc003ff == 0xf9400210
    assert branch == 0xd61f0200
    imm = ((adrp >> 29) & 3) | (((adrp >> 5) & 0x7ffff) << 2)
    if imm & (1 << 20): imm -= 1 << 21
    pointer = (stub & ~0xfff) + (imm << 12) + ((ldr >> 10) & 0xfff)*8
    target, = struct.unpack('<Q', read(blob, image, pointer, 8))
    code = read(blob, image, target, len(expected)*4)
    assert list(struct.unpack('<'+'I'*len(expected), code)) == expected, (name, code.hex())
    assert code == read(original, original_image, target+0x1000000, len(code))
    output = subprocess.run([*SSH, 'llvm-mc --disassemble --triple=aarch64'],
        input=' '.join(hex(x) for x in code)+'\n', text=True,
        capture_output=True, timeout=30, check=True).stdout
    (OUT/(name+'.txt')).write_text(hex(target)+'\n'+output)
    proof[name] = dict(stub=hex(stub), target=hex(target), bytes=code.hex(),
        original_bytes_unchanged=True, null_provider='returns UINT32_MAX' if name=='readAon' else 'returns without write')
(OUT/'original-aon-contract.json').write_text(json.dumps(dict(
    target_os='iOS16.5/20F66', provider_offset='0x88', methods=proof,
    original_kernel_sha256=hashlib.sha256(original).hexdigest(),
    original_executable_modified=False, nonnull_provider_forbidden=True), indent=2)+'\n')
remote = '/home/odin/unixnu-odin-build/evidence/odin-pmgr-u73'
subprocess.run([*SSH, 'mkdir -p '+remote], check=True)
subprocess.run([*SCP, str(DEV/'drivers/OdinPlatformPower/OdinPlatformPower.cpp'),
    str(DEV/'scripts/compile_pmgr_u73_guest.py'), 'odin@127.0.0.1:'+remote+'/'], check=True)
subprocess.run([*SSH, 'python3 '+remote+'/compile_pmgr_u73_guest.py'], check=True)
archive = OUT/'guest-evidence.tgz'
subprocess.run([*SCP, 'odin@127.0.0.1:'+remote+'/guest-evidence.tgz', str(archive)], check=True)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        assert member.isfile() and Path(member.name).name == member.name
        (OUT/member.name).write_bytes(tar.extractfile(member).read())
print('u73 original AON contract checked; source kernel rebuilt and retrieved', flush=True)
