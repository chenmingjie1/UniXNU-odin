"""Copy a host RAM Data checkpoint into a larger APFS container.

Preserve namespace, contents, permissions, owner, timestamps, BSD flags,
protection class, embedded extended attributes and volume/container UUIDs.
Omit stale Unix socket names; refuse hard links, snapshots, streamed xattrs
and all other unhandled inode types.
The original checkpoint is never modified or mounted.
"""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import stat
import struct
from prepare_launch_services_root import apfs, mkapfs, CloneVolume, index_paths, stored_payload, digest
from repair_mkapfs_spaceman import repair

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--slack-mib', type=int, default=320)
p.add_argument('--provisioned-build', help='Explicit development fixture: skip first-boot migration as ios-fuxi does; not evidence migration completed')
p.add_argument('--system-image', type=Path, help='Required with --provisioned-build to verify the actual OS build')
p.add_argument('--preferences-manifest', type=Path, help='Explicit host development preference merges; originals stay unchanged')
a = p.parse_args()
assert not a.output.exists() and a.output.resolve() != a.source.resolve()
assert 128 <= a.slack_mib <= 384
c = apfs.Container(a.source)
source_hash = digest(a.source)
v = apfs.pick_volume(c, None)
assert v.num_snapshots == 0
originals = {}
omitted_sockets = []

def clone(oid, name='', path='/'):
    inode = v.inode(oid)
    if stat.S_ISSOCK(inode.mode):
        omitted_sockets.append(path)
        return None
    assert inode.is_dir or inode.is_reg or inode.is_link, (path, inode.mode)
    if inode.is_reg:
        assert inode.nlink == 1, (path, 'hardlinks not handled')
    for key, (flags, data) in inode.xattrs.items():
        assert flags & 2 and not flags & 1 and len(data) <= 1024, (path, key, flags)
    node = mkapfs.Node(name, inode.mode, target=inode.symlink_target_bytes() if inode.is_link else None)
    node.uid, node.gid = inode.owner, inode.group
    node.original_inode = inode
    originals[path] = inode
    if inode.is_dir:
        for child_name, child_oid, _ in v.dir_entries(oid):
            child = clone(child_oid, child_name, path.rstrip('/')+'/'+child_name)
            if child is not None:
                node.children[child_name] = child
    return node

tree = clone(2)
replacements = {}
preference_changes = []
added_paths = set()
if a.preferences_manifest:
    manifest = json.loads(a.preferences_manifest.read_text())
    assert manifest['scope'] == 'Host development setup provisioning'
    assert manifest['device_commands_executed'] is False
    pref_dir = tree.children['mobile'].children['Library'].children['Preferences']
    stage = a.output.with_suffix('.preferences')
    stage.mkdir(exist_ok=False)
    for domain, update in manifest['preferences'].items():
        assert domain in ('com.apple.purplebuddy', 'com.apple.purplebuddy.notbackedup', 'com.apple.springboard')
        assert isinstance(update, dict) and update
        name = domain + '.plist'
        path = '/mobile/Library/Preferences/' + name
        before = plistlib.loads(originals[path].contents()) if path in originals else {}
        after = dict(before)
        after.update(update)
        payload = plistlib.dumps(after, fmt=plistlib.FMT_BINARY)
        if path not in originals:
            source = stage / name
            source.write_bytes(payload)
            node = mkapfs.Node(name, stat.S_IFREG | 0o600, source=str(source))
            node.uid = node.gid = 501
            pref_dir.children[name] = node
            added_paths.add(path)
        else:
            replacements[path] = payload
        preference_changes.append(dict(path=path, previous=before, merged=update, result=after))
provision = None
provision_path = '/mobile/Library/Preferences/com.apple.migration.plist'
if a.provisioned_build:
    assert a.system_image and a.provisioned_build == '20F66'
    root_c = apfs.Container(a.system_image)
    root_v = apfs.pick_volume(root_c, None)
    system_version = plistlib.loads(root_v.inode(root_v.lookup('/System/Library/CoreServices/SystemVersion.plist')[0]).contents())
    assert system_version['ProductBuildVersion'] == a.provisioned_build
    root_c.close()
    before = originals[provision_path].contents()
    preferences = plistlib.loads(before)
    assert preferences['DMUserDataDisposition']['buildVersion'] == a.provisioned_build
    assert 'LastSystemVersion' not in preferences
    preferences['LastSystemVersion'] = a.provisioned_build
    provision = plistlib.dumps(preferences, fmt=plistlib.FMT_BINARY)
    replacements[provision_path] = provision

class PreservedDataVolume(CloneVolume):
    def collect(self):
        super().collect()
        for path, payload in replacements.items():
            node = next(node for node, _ in self.items if '/'+node.path == path)
            assert node.oid not in self.inline and node.oid not in self.decmpfs
            node.size = len(payload)
            self.spool.seek(0, 2)
            self.data[node.oid] = ('spool', self.spool.tell(), len(payload))
            self.spool.write(payload)

    def fs_records(self):
        records = super().fs_records()
        nodes = {node.oid:node for node, _ in self.items}
        nodes[mkapfs.ROOT_DIR_INO] = self.root
        result = []
        existing_attrs = set()
        for key, value in records:
            packed = struct.unpack_from('<Q', key)[0]
            oid, kind = packed & ((1 << 60)-1), packed >> 60
            node = nodes.get(oid)
            if node and hasattr(node, 'original_inode') and kind == mkapfs.J_INODE:
                before = node.original_inode
                patched = bytearray(value)
                generated_flags = struct.unpack_from('<Q', patched, 48)[0]
                # Preserve observed metadata flags verbatim. Sparse file
                # bytes become allocated plain extents, so clear only the
                # independently defined sparse-storage bit in the copy.
                # Runtime also creates historical clone and purgeability
                # flags (0x10, 0x400, 0x80000), defined in the pinned
                # github-display-20261104/apfs-data-capacity/raw.h. They
                # remain metadata; stored payloads are copied independently.
                assert before.internal_flags & ~0x88658 == 0, (node.path, hex(before.internal_flags))
                assert generated_flags == 0x8000
                struct.pack_into('<Q', patched, 48, before.internal_flags & ~apfs.INODE_IS_SPARSE)
                struct.pack_into('<4Q', patched, 16, before.create_time, before.mod_time, before.change_time, before.access_time)
                struct.pack_into('<I', patched, 60, before.protection_class)
                struct.pack_into('<I', patched, 68, before.bsd_flags)
                value = bytes(patched)
            if node and hasattr(node, 'original_inode') and kind == mkapfs.J_XATTR:
                name = key[10:].split(b'\0')[0].decode()
                flags, payload = node.original_inode.xattrs[name]
                value = struct.pack('<HH', flags, len(payload))+payload
                existing_attrs.add((oid, name))
            result.append((key, value))
        for oid, node in nodes.items():
            if not hasattr(node, 'original_inode'):
                continue
            for name, (flags, payload) in node.original_inode.xattrs.items():
                if (oid, name) in existing_attrs:
                    continue
                encoded = name.encode()+b'\0'
                key = mkapfs.jkey(oid, mkapfs.J_XATTR)+struct.pack('<H', len(encoded))+encoded
                result.append((key, struct.pack('<HH', flags, len(payload))+payload))
        return sorted(result, key=lambda row:(struct.unpack_from('<Q',row[0])[0] & ((1<<60)-1), self.sort_key(row)))

class PreservedDataContainer(mkapfs.Container):
    def uuid(self, what):
        if what == 'container':
            return c.nx['uuid']
        if what == 'volume 0':
            return v.vol_uuid
        return super().uuid(what)

raw = a.output.with_suffix('.unrepaired.apfs')
with a.output.with_suffix('.spool').open('w+b') as spool:
    volume = PreservedDataVolume(0, v.volname, tree, False, 1683900000000000000, spool, [])
    writer = PreservedDataContainer([volume], a.slack_mib*256, 'UniXNUHostData-expanded')
    writer.layout()
    assert writer.block_count * 4096 <= 0x20000000
    writer.write(str(raw))
repair(raw, a.output)
check_c = apfs.Container(a.output)
check_v = apfs.pick_volume(check_c, None)
paths = index_paths(check_v)
assert set(paths) == set(originals) | added_paths
xattrs = 0
for path, before in originals.items():
    after = check_v.inode(paths[path][0])
    assert (after.mode, after.owner, after.group, after.bsd_flags, after.protection_class) == (before.mode, before.owner, before.group, before.bsd_flags, before.protection_class), path
    assert (after.create_time,after.mod_time,after.change_time,after.access_time)==(before.create_time,before.mod_time,before.change_time,before.access_time),path
    assert after.xattrs == before.xattrs, path
    assert after.internal_flags == before.internal_flags & ~apfs.INODE_IS_SPARSE, path
    xattrs += len(before.xattrs)
    if before.is_reg:
        if provision is not None and path == provision_path:
            assert after.contents() == provision
            old = plistlib.loads(before.contents())
            new = plistlib.loads(after.contents())
            assert new.pop('LastSystemVersion') == a.provisioned_build
            assert old == new
        elif path in replacements:
            assert after.contents() == replacements[path], path
        else:
            assert stored_payload(after)==stored_payload(before),path
    if before.is_link:
        assert after.symlink_target_bytes()==before.symlink_target_bytes(),path
assert check_v.vol_uuid==v.vol_uuid and check_c.nx['uuid']==c.nx['uuid']
for change in preference_changes:
    inode = check_v.inode(paths[change['path']][0])
    assert plistlib.loads(inode.contents()) == change['result'], change['path']
    if change['path'] in added_paths:
        assert (inode.mode, inode.owner, inode.group) == (stat.S_IFREG | 0o600, 501, 501)
assert digest(a.source) == source_hash
record = dict(source=str(a.source), source_sha256=source_hash,
    output=str(a.output), sha256=digest(a.output), bytes=a.output.stat().st_size,
    namespace_entries_preserved=len(originals), extended_attributes_preserved=xattrs,
    stale_unix_socket_names_omitted=omitted_sockets,
    all_file_payloads_verified=True, permissions_owners_timestamps_flags_verified=True,
    intentionally_modified_file_count=len(replacements),
    intentionally_added_file_paths=sorted(added_paths),
    development_preference_changes=preference_changes,
    metadata_inode_flags_preserved=True, sparse_contents_copied_to_allocated_extents=True,
    volume_and_container_uuids_preserved=True, source_checkpoint_unchanged=True,
    migration_complete_marker_injected=provision is not None,
    first_boot_migration_intentionally_skipped=provision is not None,
    real_migration_completed_claim=False, provisioned_build=a.provisioned_build,
    provisioned_preference_path=provision_path if provision is not None else None,
    device_commands_executed=False,
    runtime_verified=False, scope='Larger copied QEMU Data checkpoint; not phone storage')
a.output.with_suffix('.preservation.json').write_text(json.dumps(record,indent=2)+'\n')
check_c.close()
c.close()
print(json.dumps(record,indent=2))
