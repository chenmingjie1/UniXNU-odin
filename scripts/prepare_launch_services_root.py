"""Clone the local APFS fixture and supply its missing launchd job directory.

Existing regular-file payloads (including compressed forks and CodeDirectories)
are copied verbatim. No executable or signature is rewritten. This prepares a
host-only fixture; it does not mount a Data volume or qualify phone hardware.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import plistlib
import stat
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/hakios-upstream/tools/apfs'))
import apfs
import mkapfs
from repair_mkapfs_spaceman import repair


def upstream_core_labels():
    """Read the pinned MIT upstream policy as data; never execute fetched code."""
    source = ROOT / ('work/UniXNU-odin/research/github-display-20261104/'
        'bangprovn--ios-fuxi/source/ios-fuxi-27f6a31c8b27c6f9127f9cf27092968422579ccf/'
        'tools/launchd-on-demand.py')
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '70654391de0b31d3da70dd5db57625dfc7d518fda303982225475f0b758c3a0c'
    assignments = [node for node in ast.parse(raw).body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'KEEP' for target in node.targets)]
    assert len(assignments) == 1
    return set(ast.literal_eval(assignments[0].value))


class BinaryImage:
    def __init__(self, path):
        self.stream = open(path, 'rb')
        self.size = Path(path).stat().st_size
    def read(self, offset, length):
        self.stream.seek(offset)
        return self.stream.read(length)
    def close(self):
        self.stream.close()


apfs.RawImage = BinaryImage


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def index_paths(volume):
    """Index each directory once; repeated lookup reparses large directories."""
    entries = {'/': (2, 4)}
    def walk(oid, prefix):
        for name, child_oid, dtype in volume.dir_entries(oid):
            path = prefix + '/' + name
            assert path not in entries
            entries[path] = (child_oid, dtype)
            if dtype == 4:
                walk(child_oid, path)
    walk(2, '')
    return entries


def stored_payload(inode):
    header = inode.decmpfs
    if header:
        codec = struct.unpack_from('<I', header, 4)[0]
        if codec == 3:
            return 'inline', header
        assert codec == 4, codec
        return 'rsrc', inode.vol.xattr_bytes(inode.obj_id, apfs.RSRC_FORK_XATTR_NAME)
    return 'plain', inode.contents()


class CloneVolume(mkapfs.Volume):
    def collect(self):
        self.items = []
        self.root.oid = mkapfs.ROOT_DIR_INO
        def walk(node, path):
            for name, child in sorted(node.children.items()):
                child.oid = self.new_oid()
                child.path = path + name
                self.items.append((child, node.oid))
                if stat.S_ISDIR(child.mode):
                    walk(child, child.path + '/')
        walk(self.root, '')
        self.data, self.inline, self.decmpfs = {}, {}, {}
        self.preserved = {}
        for node, _ in self.items:
            if not stat.S_ISREG(node.mode):
                continue
            if hasattr(node, 'original_inode'):
                node.size = node.original_inode.size
                kind, payload = stored_payload(node.original_inode)
                header = node.original_inode.decmpfs
                self.preserved[node.path] = {
                    'kind': kind, 'bytes': node.size,
                    'stored_sha256': hashlib.sha256(payload).hexdigest(),
                    'decmpfs': header.hex() if header else None,
                }
            else:
                payload = Path(node.source).read_bytes()
                node.size, kind = len(payload), 'plain'
            if kind == 'inline':
                self.inline[node.oid] = payload
            elif payload:
                sid = self.new_oid() if kind == 'rsrc' else node.oid
                self.spool.seek(0, 2)
                self.data[sid] = ('spool', self.spool.tell(), len(payload))
                self.spool.write(payload)
                if kind == 'rsrc':
                    self.decmpfs[node.oid] = (header, sid)
            del payload


JOBS = '''com.apple.notifyd com.apple.cfprefsd.xpc.daemon
com.apple.cfprefsd.xpc.daemon.system com.apple.logd com.apple.syslogd
com.apple.distnoted.xpc.daemon com.apple.diagnosticd com.apple.fseventsd
com.apple.containermanagerd com.apple.containermanagerd.system
com.apple.runningboardd com.apple.backboardd com.apple.mobile.usermanagerd
com.apple.mobilegestalt.xpc com.apple.lsd com.apple.powerd com.apple.analyticsd
com.apple.logd_helper com.apple.iconservices.iconservicesagent
com.apple.pluginkit.pkd com.apple.SpringBoard'''.split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--console-stderr', action='store_true',
                        help='Diagnostic control only: redirect jobs to root-owned /dev/console')
    parser.add_argument('--extend-existing', action='store_true',
                        help='Preserve the existing fixture and add only explicitly named original jobs')
    parser.add_argument('--job', action='append',
                        help='Exact original launchd label; may be specified more than once')
    parser.add_argument('--publish-on-demand',action='store_true',
                        help='Publish missing original jobs with autostart removed, as ios-fuxi launchd-on-demand.py does')
    parser.add_argument('--restore-core-autostart', action='store_true',
                        help='Restore original autostart only for the pinned upstream KEEP policy')
    args = parser.parse_args()
    assert args.source.resolve() != args.target.resolve()
    assert not args.target.exists()
    stage = args.target.with_suffix('.staging')
    stage.mkdir(exist_ok=False)
    container = apfs.Container(args.source)
    volume = apfs.pick_volume(container, None)
    def clone(oid, name=''):
        inode = volume.inode(oid)
        node = mkapfs.Node(name, inode.mode,
                           target=inode.symlink_target_bytes() if inode.is_link else None)
        node.uid, node.gid = inode.owner, inode.group
        if inode.is_reg:
            node.original_inode = inode
        elif inode.is_dir:
            for child_name, child_oid, _ in volume.dir_entries(oid):
                node.children[child_name] = clone(child_oid, child_name)
        else:
            assert inode.is_link, ('Unsupported inode type', oid, inode.mode)
        return node
    tree = clone(2)
    redwood = tree.children['redwood']
    if args.extend_existing:
        assert args.job or args.publish_on_demand or args.restore_core_autostart, 'Explicit job policy required'
        jobs_dir=redwood.children['LaunchDaemons']
        assert stat.S_ISDIR(jobs_dir.mode)
    else:
        jobs_dir = mkapfs.Node('LaunchDaemons', stat.S_IFDIR | 0o755)
        assert not redwood.children
        redwood.children['LaunchDaemons'] = jobs_dir
    link = tree.children['System'].children['Library'].children['LaunchDaemons']
    assert link.target == b'/redwood/LaunchDaemons'
    library = tree.children['System'].children['Library']
    # launchd rejects DYLD_* job environment variables. Supply the normal
    # filesystem cache path instead, for every exec (including xpcproxy).
    caches = library.children.setdefault('Caches', mkapfs.Node('Caches', stat.S_IFDIR | 0o755))
    if args.extend_existing:
        assert caches.children['com.apple.dyld'].target==b'/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld'
    else:
        assert 'com.apple.dyld' not in caches.children
        caches.children['com.apple.dyld'] = mkapfs.Node('com.apple.dyld', stat.S_IFLNK | 0o755,
            target=b'/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld')
    reports = []
    skipped=[]
    source_dir=ROOT/'work/ios-inputs/rootfs/System/Library/LaunchDaemons'
    core_labels = upstream_core_labels() if args.publish_on_demand or args.restore_core_autostart else set()
    if args.restore_core_autostart:
        assert args.extend_existing and not args.job and not args.publish_on_demand
        job_sources=[]
        for source in sorted(source_dir.glob('*.plist')):
            original=plistlib.loads(source.read_bytes())
            if original.get('Label') not in core_labels or source.name not in jobs_dir.children:
                continue
            current=plistlib.loads(jobs_dir.children[source.name].original_inode.contents())
            assert current['Label']==original['Label']
            expected=dict(original)
            expected['EnvironmentVariables']=dict(expected.get('EnvironmentVariables',{}),OS_ACTIVITY_DT_MODE='YES')
            if current != expected:
                # Only undo this tool's removed autostart keys. Refuse to
                # replace any unrelated existing configuration difference.
                check=dict(expected)
                for key in ('RunAtLoad','KeepAlive','StartInterval','StartCalendarInterval',
                            'WatchPaths','QueueDirectories','StartOnMount','LaunchEvents'):
                    if key not in current:check.pop(key,None)
                assert current==check, source.name
                job_sources.append((original['Label'],source))
        assert job_sources, 'No core autostart discrepancy to restore'
    elif args.publish_on_demand:
        assert args.extend_existing and not args.job
        seen_labels=set()
        for node in jobs_dir.children.values():
            original=plistlib.loads(node.original_inode.contents())
            seen_labels.add(original['Label'])
        job_sources=[]
        for original in sorted(source_dir.glob('*.plist')):
            if original.name in jobs_dir.children:continue
            job=plistlib.loads(original.read_bytes())
            label=job.get('Label');program=job.get('Program') or job.get('ProgramArguments',[None])[0]
            if not isinstance(label,str) or not label.startswith('com.apple.') or not program or not volume.lookup(program):
                skipped.append(dict(file=original.name,label=label,program=program,
                                    reason='No original service label or executable in this root'))
                continue
            if label in seen_labels:
                skipped.append(dict(file=original.name,label=label,program=program,
                                    reason='Original service label already published'))
                continue
            seen_labels.add(label);job_sources.append((label,original))
    else:
        labels=args.job or JOBS
        assert len(labels)==len(set(labels))
        job_sources=[(label,source_dir/(label+'.plist')) for label in labels]
    for label,source in job_sources:
        assert label.startswith('com.apple.') and '/' not in label and '\\' not in label
        assert args.restore_core_autostart or source.name not in jobs_dir.children, 'Do not overwrite an existing job'
        data = source.read_bytes()
        job = plistlib.loads(data)
        assert job['Label'] == label
        program = job.get('Program') or job['ProgramArguments'][0]
        assert volume.lookup(program), program
        changes = ['EnvironmentVariables.OS_ACTIVITY_DT_MODE']
        if args.restore_core_autostart:
            changes.append('restored original autostart for pinned upstream KEEP label')
        if args.publish_on_demand and label not in core_labels:
            # Same autostart keys as the pinned ios-fuxi launchd-on-demand.py
            # (MIT, adapted from HakiOS). Existing core jobs are preserved.
            # Original MachServices, sockets, entitlements and Disabled state
            # remain in the original job; only missing jobs are added here.
            for key in ('RunAtLoad','KeepAlive','StartInterval','StartCalendarInterval',
                        'WatchPaths','QueueDirectories','StartOnMount','LaunchEvents'):
                if key in job:
                    del job[key];changes.append('removed autostart '+key)
        if args.console_stderr:
            job['StandardErrorPath'] = '/dev/console'
            changes.append('StandardErrorPath')
        job.setdefault('EnvironmentVariables', {})['OS_ACTIVITY_DT_MODE'] = 'YES'
        target = stage / source.name
        target.write_bytes(plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
        jobs_dir.children[source.name] = mkapfs.Node(source.name, stat.S_IFREG | 0o644, source=str(target))
        reports.append({'label': label, 'program': program,
                        'filename':source.name,
                        'source_sha256': hashlib.sha256(data).hexdigest(),
                        'output_sha256': digest(target),
                        'changes': changes})
    print('Prepared', len(reports), 'original service configurations', flush=True)
    raw = args.target.with_suffix('.unrepaired.apfs')
    with args.target.with_suffix('.spool').open('w+b') as spool:
        cloned = CloneVolume(0, 'UniXNUHostSystem', tree, True, 1683900000000000000, spool, [])
        writer = mkapfs.Container([cloned], 256, 'UniXNUHostServices-u11')
        writer.layout()
        writer.write(str(raw))
        print('Cloned', len(cloned.preserved), 'existing file payloads', flush=True)
    repair(raw, args.target)
    check_container = apfs.Container(args.target)
    check = apfs.pick_volume(check_container, None)
    checked_paths = index_paths(check)
    for path, expected in cloned.preserved.items():
        inode = check.inode(checked_paths['/' + path][0])
        kind, payload = stored_payload(inode)
        header = inode.decmpfs
        assert inode.size == expected['bytes'] and kind == expected['kind'], path
        assert hashlib.sha256(payload).hexdigest() == expected['stored_sha256'], path
        assert (header.hex() if header else None) == expected['decmpfs'], path
    for row in reports:
        path = '/redwood/LaunchDaemons/' + row['filename']
        assert hashlib.sha256(check.inode(checked_paths[path][0]).contents()).hexdigest() == row['output_sha256']
    record = {'source': str(args.source), 'source_sha256': digest(args.source),
              'output': str(args.target), 'sha256': digest(args.target),
              'bytes': args.target.stat().st_size, 'existing_file_payloads_preserved': len(cloned.preserved),
              'all_existing_stored_file_payloads_verified': True,
              'executables_modified': False, 'services': reports,
              'publish_on_demand':args.publish_on_demand,'skipped_jobs':skipped,
              'restore_core_autostart':args.restore_core_autostart,
              'standard_shared_cache_path_supplied': True,
              'diagnostic_console_stderr': args.console_stderr,
              'data_volume_mounted': False, 'device_commands_executed': False,
              'scope': 'Host QEMU service-loading fixture; not a phone desktop image'}
    args.target.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    check_container.close()
    container.close()
    # The generated intermediate files remain available for audit.
    print(json.dumps({k: record[k] for k in ('bytes', 'sha256', 'existing_file_payloads_preserved')}))


if __name__ == '__main__':
    main()
