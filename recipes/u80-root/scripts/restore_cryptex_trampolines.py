"""Restore the two standalone Cryptex trampoline library paths in a host root copy."""
from pathlib import Path
import argparse
import hashlib
import json
import stat
import prepare_launch_services_root as base

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('target', type=Path)
parser.add_argument('--verify-existing', action='store_true',
                    help='Read-only recovery audit of an already written target')
args = parser.parse_args()
assert args.source.resolve() != args.target.resolve()
assert args.target.exists() if args.verify_existing else not args.target.exists()
container = base.apfs.Container(args.source)
volume = base.apfs.pick_volume(container, None)


def clone(oid, name=''):
    inode = volume.inode(oid)
    node = base.mkapfs.Node(name, inode.mode,
        target=inode.symlink_target_bytes() if inode.is_link else None)
    node.uid, node.gid = inode.owner, inode.group
    if inode.is_reg:
        node.original_inode = inode
    elif inode.is_dir:
        for child_name, child_oid, _ in volume.dir_entries(oid):
            node.children[child_name] = clone(child_oid, child_name)
    else:
        assert inode.is_link, (oid, inode.mode)
    return node


tree = clone(2)
library = tree.children['usr'].children['lib']
links = []
for name in ['libobjc-trampolines.dylib', 'libffi-trampolines.dylib']:
    source = '/usr/lib/' + name
    target = '/System/Cryptexes/OS/usr/lib/' + name
    assert volume.lookup(source) is None and name not in library.children
    target_inode = volume.inode(volume.lookup(target)[0])
    assert target_inode.is_reg and target_inode.mode & 0o111
    library.children[name] = base.mkapfs.Node(name, stat.S_IFLNK | 0o755,
                                            target=target.encode())
    links.append({'path': source, 'target': target,
                  'target_sha256': hashlib.sha256(target_inode.contents()).hexdigest()})
raw = args.target.with_suffix('.unrepaired.apfs')
if not args.verify_existing:
    assert not raw.exists() and not args.target.with_suffix('.spool').exists()
    with args.target.with_suffix('.spool').open('w+b') as spool:
        copied = base.CloneVolume(0, 'UniXNUHostSystem', tree, True,
                                 1683900000000000000, spool, [])
        writer = base.mkapfs.Container([copied], 256, 'UniXNUHostCryptex-u13')
        writer.layout()
        writer.write(str(raw))
    base.repair(raw, args.target)
print('Cloned root; checking all existing stored payloads', flush=True)
check_container = base.apfs.Container(args.target)
check = base.apfs.pick_volume(check_container, None)
checked_paths = base.index_paths(check)
preserved_count = 0


def verify(node, path=''):
    global preserved_count
    if hasattr(node, 'original_inode'):
        original = node.original_inode
        inode = check.inode(checked_paths[path][0])
        kind, payload = base.stored_payload(inode)
        old_kind, old_payload = base.stored_payload(original)
        assert inode.size == original.size and kind == old_kind, path
        assert hashlib.sha256(payload).digest() == hashlib.sha256(old_payload).digest(), path
        assert inode.decmpfs == original.decmpfs, path
        assert (inode.mode, inode.owner, inode.group) == (original.mode, original.owner, original.group), path
        preserved_count += 1
    for name, child in node.children.items():
        verify(child, path + '/' + name)


verify(tree)
for row in links:
    inode = check.inode(checked_paths[row['path']][0])
    assert inode.is_link and inode.symlink_target_bytes() == row['target'].encode()
    inode = check.inode(checked_paths[row['target']][0])
    assert hashlib.sha256(inode.contents()).hexdigest() == row['target_sha256']
receipt = {
    'scope': 'Computer-only host root copy; no phone operations',
    'source': str(args.source), 'source_sha256': base.digest(args.source),
    'output': str(args.target), 'sha256': base.digest(args.target),
    'bytes': args.target.stat().st_size, 'links': links,
    'existing_file_payloads_preserved': preserved_count,
    'all_existing_stored_file_payloads_verified': True,
    'executables_modified': False, 'runtime_path_fix_verified': False,
    'device_commands_executed': False,
}
args.target.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
check_container.close()
container.close()
print(json.dumps(receipt, indent=2))
