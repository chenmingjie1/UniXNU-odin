"""Add explicit board-owned handoff properties without altering hardware data.

This stages computer-only work. It neither enables a desktop by itself nor
issues device commands. Existing properties must agree; no silent overrides.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import tomllib
from adt_codec import decode,encode

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
source = dev / 'build/prelinked-payload-u08/esp/EFI/UniXNU/Payloads/kernel.macho.adt'
config = dev / 'configs/odin-desktop-handoff.toml'
output = dev / 'build/desktop-handoff'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel',type=Path,default=dev/'build/ios16-prelink-u09root/kernel.prelinked.experimental.macho')
parser.add_argument('--system',type=Path,default=root/'outputs/MIX4-iOS16.5-touch-userland-r64-input-sampler/images/system.apfs')
parser.add_argument('--ramdisk-slot',action='store_true')
parser.add_argument('--output-dir',type=Path,default=output)
args = parser.parse_args()
output=args.output_dir
output.mkdir(parents=True,exist_ok=True)
data = source.read_bytes()

tree = decode(data)
chosen = next(props for props, nodes in tree[1] if props['name'] == b'chosen\0')
additions = tomllib.loads(config.read_text())['chosen']['u32']
for name, value in additions.items():
    packed = struct.pack('<I', value)
    assert name not in chosen or chosen[name] == packed, name
    chosen[name] = packed
chosen_node = next(item for item in tree[1] if item[0]['name'] == b'chosen\0')
manifest = next(props for props, nodes in chosen_node[1] if props['name'] == b'manifest-properties\0')
# AppleImage4's original 20F66 code reads BNCH as up to 48 bytes from this
# node. Supply the digest of this payload's own development nonce, never a
# fabricated Apple boot manifest or a reused all-zero nonce. The source ADT
# generator obtained random-seed from the host CSPRNG.
seed = chosen['random-seed']
assert len(seed) >= 64
nonce = hashlib.sha256(b'UniXNU.odin.development-nonce.v1\0' + seed).digest()
nonce_hash = hashlib.sha384(nonce).digest()
assert 'BNCH' not in manifest or manifest['BNCH'] == nonce_hash
manifest['BNCH'] = nonce_hash
chosen['odin-development-boot'] = struct.pack('<I', 1)
# Bind the intended development boot set to the actual local inputs. This
# owner manifest is not an Apple IM4M signature or a claim of runtime trust.
def digest_file(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8*1024*1024):
            sha.update(chunk)
    return {'bytes':path.stat().st_size,'sha256':sha.hexdigest()}
bootset = {'domain':'UniXNU.odin.DevelopmentBootSet.v1',
           'files':{'kernel.macho':digest_file(args.kernel),
                    'system.apfs':digest_file(args.system),
                    'base.adt':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},
                    'handoff.toml':digest_file(config)}}
canonical = json.dumps(bootset,sort_keys=True,separators=(',',':')).encode()
owner_hash = hashlib.sha384(canonical).digest()
chosen['boot-manifest-hash'] = owner_hash
chosen['owner-boot-manifest-domain'] = bootset['domain'].encode()+b'\0'
if args.ramdisk_slot:
    mappings = next(props for props,nodes in chosen_node[1] if props['name']==b'memory-map\0')
    assert 'RAMDisk' not in mappings
    mappings['RAMDisk'] = bytes(16)
result = encode(tree)
(output / 'kernel.macho.adt').write_bytes(result)
(output / 'bootset-manifest.json').write_bytes(canonical)
report = {
    'base_sha256': hashlib.sha256(data).hexdigest(),
    'output_sha256': hashlib.sha256(result).hexdigest(),
    'config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
    'chosen_additions_u32': additions,
    'manifest_properties': {'BNCH': nonce_hash.hex()},
    'owner_bootset_sha384':owner_hash.hex(),
    'ramdisk_slot':args.ramdisk_slot,
    'nonce_provenance': 'SHA384 of a domain-separated nonce derived from the source ADT CSPRNG seed; development boot only',
    'meaning': 'Explicit unlocked development policy; no Apple attestation asserted',
    'encoding_evidence': '../ios16-prelink-u09/policy-getter.txt',
    'hardware_properties_changed': False,
    'device_commands_executed': False,
    'desktop_verified': False,
}
(output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
