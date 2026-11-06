"""Build an isolated APFS Data seed from the extracted iOS directory skeleton.

The seed is for a separate, writable QEMU RAM device. It is never a partition
image, does not contain personal phone data, and is not mounted by this script.
"""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/hakios-upstream/tools/apfs'))
import mkapfs
from repair_mkapfs_spaceman import repair

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--slack-mib', type=int, default=128)
args = parser.parse_args()
assert 64 <= args.slack_mib <= 512 and not args.output.exists()
stage = args.output.with_suffix('.staging')
stage.mkdir(exist_ok=False)
manifest = []
for raw in (ROOT / 'work/ios-inputs/var.skel').read_text().splitlines():
    f = raw.split('\t')
    if f[0] == 'd':
        kind, mode, uid, gid, path = f
        assert path.startswith('/private/var/')
        rel = path.removeprefix('/private/var/')
        (stage / rel).mkdir(parents=True, exist_ok=True)
        manifest.append('\t'.join(['4' + mode.zfill(4), uid, gid, rel, '']))
    elif f[0] == 'l':
        _, target, path = f
        assert path.startswith('/private/var/')
        manifest.append('\t'.join(['120777', '0', '0', path.removeprefix('/private/var/'), target]))
    else:
        raise AssertionError(f)
# Match the base filesystem root convention and create basic log destinations.
manifest.extend(['41777\t0\t0\ttmp\t', '40755\t0\t0\trun\t'])
for path in ['db/diagnostics/.migrated', 'db/diagnostics/timesync/.migrated', 'db/uuidtext/.migrated']:
    dest = stage / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b'')
    manifest.append('100644\t0\t0\t' + path + '\t')
# Setup completion is a fixture preference, not device activation.
preferences = stage / 'mobile/Library/Preferences/com.apple.purplebuddy.plist'
preferences.parent.mkdir(parents=True, exist_ok=True)
preferences.write_bytes(plistlib.dumps({'SetupDone': True, 'SetupFinishedAllSteps': True}, fmt=plistlib.FMT_BINARY))
manifest.append('100600\t501\t501\tmobile/Library/Preferences/com.apple.purplebuddy.plist\t')
manifest_path = args.output.with_suffix('.manifest')
manifest_path.write_text('\n'.join(manifest) + '\n')
tree = mkapfs.read_tree(stage)
mkapfs.apply_manifest(tree, manifest_path)
volume = mkapfs.Volume(0, 'UniXNUHostData', tree, False, 1683900000000000000, None, [])
container = mkapfs.Container([volume], args.slack_mib * 256, 'UniXNUHostData-u11')
container.layout()
raw = args.output.with_suffix('.unrepaired.apfs')
container.write(str(raw))
repair(raw, args.output)
with args.output.open('rb') as stream:
    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
record = {'scope': 'Isolated host QEMU writable RAM Data seed', 'bytes': args.output.stat().st_size,
          'sha256': sha, 'skeleton_records': len(manifest), 'seed_volume_uuid_bytes': container.uuid('volume 0').hex(),
          'device_commands_executed': False, 'rw_mount_verified': False,
          'setup_preferences_are_activation': False}
args.output.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
