"""Copy host system and add one finite virtual-input job and audited tool.

No original executable is modified. The resulting fixture is QEMU only.
"""
from pathlib import Path
import hashlib
import json
import plistlib
import stat
import struct
import argparse
from prepare_launch_services_root import apfs, mkapfs, CloneVolume, index_paths, stored_payload, digest
from repair_mkapfs_spaceman import repair

DEV = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', default='u50')
p.add_argument('--sb-unlock-library', action='store_true')
args = p.parse_args()
assert args.tag.isalnum()
source = DEV / 'build/root-media/system-core-policy-u37.apfs'
tool_dir = DEV / ('build/host-virtual-input-' + args.tag)
tool = tool_dir / 'host_swipe'
audit = json.loads((tool_dir / 'tool-audit.json').read_text())[0]
assert digest(tool) == audit['sha256'] and audit['code_directories']
assert all(not d['page_hash_mismatches'] for d in audit['code_directories'])
build_record = json.loads((tool_dir / 'build.json').read_text())
assert (build_record['tool_kind'] == 'sb-unlock-library') == args.sb_unlock_library
out = DEV / ('build/root-media/system-host-input-' + args.tag + '.apfs')
assert not out.exists()
c = apfs.Container(source)
v = apfs.pick_volume(c, None)
source_paths = index_paths(v)
def clone(oid, name=''):
    inode = v.inode(oid)
    node = mkapfs.Node(name, inode.mode, target=inode.symlink_target_bytes() if inode.is_link else None)
    node.uid, node.gid = inode.owner, inode.group
    if inode.is_reg:
        node.original_inode = inode
    elif inode.is_dir:
        for child_name, child_oid, _ in v.dir_entries(oid):
            node.children[child_name] = clone(child_oid, child_name)
    else:
        assert inode.is_link
    return node
tree = clone(2)
redwood = tree.children['redwood']
assert 'host-input' not in redwood.children
directory = mkapfs.Node('host-input', stat.S_IFDIR | 0o755)
tool_name = 'libodin-ui-unlock.dylib' if args.sb_unlock_library else 'host_swipe'
directory.children[tool_name] = mkapfs.Node(tool_name, stat.S_IFREG | 0o755, source=str(tool))
redwood.children['host-input'] = directory
if args.sb_unlock_library:
    assert audit['filetype'] == 6
    label = 'com.apple.SpringBoard'
    job_file = tool_dir / (label + '.plist')
    job_path = '/redwood/LaunchDaemons/' + job_file.name
    job = plistlib.loads(v.inode(source_paths[job_path][0]).contents())
    original_job = plistlib.loads(plistlib.dumps(job))
    env = job.setdefault('EnvironmentVariables', {})
    assert 'DYLD_INSERT_LIBRARIES' not in env
    env['DYLD_INSERT_LIBRARIES'] = '/redwood/host-input/' + tool_name
    job_file.write_bytes(plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
    node = redwood.children['LaunchDaemons'].children[job_file.name]
    del node.original_inode
    node.source = str(job_file)
else:
    label = 'org.unixnu.odin.host-input-test'
    job = dict(Label=label, ProgramArguments=['/redwood/host-input/host_swipe'], RunAtLoad=True, KeepAlive=False,
               UserName='root', StandardErrorPath='/private/var/tmp/odin-host-input.log',
               StandardOutPath='/private/var/tmp/odin-host-input.log', ProcessType='Background')
    job_file = tool_dir / (label + '.plist')
    job_file.write_bytes(plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
    assert job_file.name not in redwood.children['LaunchDaemons'].children
    redwood.children['LaunchDaemons'].children[job_file.name] = mkapfs.Node(job_file.name, stat.S_IFREG | 0o644, source=str(job_file))
raw = out.with_suffix('.unrepaired.apfs')
with out.with_suffix('.spool').open('w+b') as spool:
    cloned = CloneVolume(0, 'UniXNUHostSystem', tree, True, 1683900000000000000, spool, [])
    writer = mkapfs.Container([cloned], 256, 'UniXNUHostInput-' + args.tag)
    writer.layout()
    writer.write(str(raw))
repair(raw, out)
check_c = apfs.Container(out)
check = apfs.pick_volume(check_c, None)
paths = index_paths(check)
added = {'/redwood/host-input', '/redwood/host-input/' + tool_name}
if not args.sb_unlock_library:
    added.add('/redwood/LaunchDaemons/' + job_file.name)
assert set(paths) == set(source_paths) | added
for path, expected in cloned.preserved.items():
    inode = check.inode(paths['/' + path][0])
    kind, payload = stored_payload(inode)
    assert inode.size == expected['bytes'] and kind == expected['kind']
    assert hashlib.sha256(payload).hexdigest() == expected['stored_sha256'], path
    assert (inode.decmpfs.hex() if inode.decmpfs else None) == expected['decmpfs'], path
assert digest(tool) == hashlib.sha256(check.inode(paths['/redwood/host-input/' + tool_name][0]).contents()).hexdigest()
assert plistlib.loads(check.inode(paths['/redwood/LaunchDaemons/' + job_file.name][0]).contents()) == job
if args.sb_unlock_library:
    restored = plistlib.loads(plistlib.dumps(job))
    del restored['EnvironmentVariables']['DYLD_INSERT_LIBRARIES']
    assert restored == original_job
check_c.close()
c.close()
trust_source = DEV / 'build/root-media/full-development-trust-u39.bundle'
trust = trust_source.read_bytes()
assert hashlib.sha256(trust).hexdigest() == '78e53c93b54354a93c4bdb59cc9dc5863b003e282406cff32a2262d8d9f71f7b'
assert struct.unpack_from('<2I', trust) == (1, 8)
version, _, count = struct.unpack_from('<I16sI', trust, 8)
assert version == 2 and len(trust) == 32 + count * 24
entries = {trust[i:i+24] for i in range(32, len(trust), 24)}
for cd in audit['code_directories']:
    entries.add(bytes.fromhex(cd['cdhash']) + struct.pack('<4B', cd['hash_type'], 0, 0, 0))
ordered = b''.join(sorted(entries))
identifier = hashlib.sha256(b'UniXNU.Odin.HostInput\0' + args.tag.encode() + ordered).digest()[:16]
bundle = struct.pack('<3I16sI', 1, 8, 2, identifier, len(entries)) + ordered
trust_out = DEV / ('build/root-media/host-input-development-trust-' + args.tag + '.bundle')
assert not trust_out.exists()
trust_out.write_bytes(bundle)
record = dict(scope='Host-only virtual input fixture; not a phone image', source=str(source), source_sha256=digest(source),
    output=str(out), sha256=digest(out), bytes=out.stat().st_size, added_paths=sorted(added),
    original_file_payloads_verified=len(cloned.preserved), original_executables_modified=False,
    job=job, tool_kind=build_record['tool_kind'], tool_sha256=digest(tool), trust_source_sha256=digest(trust_source), trust_entries=len(entries),
    trust_output=str(trust_out), trust_sha256=digest(trust_out), wildcard_trust=False,
    device_commands_executed=False, virtual_input_runtime_verified=False, desktop_verified=False)
out.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
