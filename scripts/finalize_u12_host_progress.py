"""Record actual host Data I/O and service execution, without phone claims."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import re
import shutil
import struct

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--service-run', required=True)
parser.add_argument('--system', type=Path, default=dev / 'build/root-media/system-launch-services-u12.apfs')
parser.add_argument('--trust', type=Path, default=dev / 'build/root-media/services-development-trust-u12.bundle')
args = parser.parse_args()
assert args.service_run.isalnum()
run = dev / ('build/qemu-early-entry-' + args.service_run)
out = root / 'outputs/MIX4-UniXNU-host-u12'
out.mkdir(exist_ok=True)
load = lambda path: json.loads(path.read_text())
relative = lambda path: path.resolve().relative_to(root).as_posix()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def integer(name, size=4, signed=False):
    return int.from_bytes((run / ('symbol-' + name + '.bin')).read_bytes()[:size],
                          'little', signed=signed)


replay = load(run / 'verification.json')
kernel_dir = dev / 'build/ios16-prelink-u12match'
audit = load(kernel_dir / 'independent-audit.json')
assert audit['passed'] and audit['candidate_sha256'] == replay['kernel_sha256']
data = {
    'stage': integer('_native_owner_data_stage'),
    'status': integer('_native_owner_data_status', signed=True),
    'readonly': integer('_native_owner_data_readonly', signed=True),
    'provider_ready': integer('_native_ram_block_ready'),
    'reads': integer('_native_ram_block_reads', 8),
    'writes': integer('_native_ram_block_writes', 8),
    'io_failures': integer('_native_ram_block_failures', 8),
}
assert data['stage'] == 4 and data['status'] == 0 and data['readonly'] == 0
assert data['provider_ready'] == 1 and data['reads'] > 0 and data['writes'] > 0
assert data['io_failures'] == 0
assert all(row['matches_input'] for row in load(run / 'loaded-data-media.json'))
assert all(row['matches_input'] for row in load(run / 'loaded-media.json'))
calls = load(run / 'syscalls.json')
logs = load(run / 'printf.json')
user_log = ''.join(row.get('write_text', '') for row in calls)
(run / 'userspace.log').write_text(user_log, encoding='utf8')
(out / 'userspace.log').write_text(user_log, encoding='utf8')
spawned = sorted(set(re.findall(r'Successfully spawned (\S+)', user_log)))
failures = sorted(set(re.findall(r'Service could not initialize: ([^\n]+)', user_log)))
exit_reasons = sorted(set(re.findall(r'\(([^\n)]+)\) <Notice>: (exited (?:with exit reason|due to) [^\r\n]+)', user_log)))
signature_rejections = sorted(set(row.get('strings', {}).get('0', '<unnamed>')
    for row in logs if 'rejecting signature' in row.get('format', '')))
service_states = {}
for match in re.finditer(r'\((?:user/\d+|system)/([^ )]+)(?: \[\d+\])?\) <Notice>: service state: ([^\r\n]+)', user_log):
    service_states[match[1]] = match[2]
cache_rejections = [row for row in logs if 'Adhoc signed binary' in str(row)]
assert not cache_rejections
abi = load(dev / 'build/native-kernel/odin-storage-abi-u12/interface-static-audit.json')
assert abi['candidate_sha256'] == replay['kernel_sha256']
assert abi['method_slots'] == 190 and abi['kernel_bindings'] == 176
root_path = args.system
media = load(root_path.with_suffix('.json'))
assert not media['executables_modified']
assert media['all_existing_stored_file_payloads_verified']
assert replay['ramdisk_bytes'] == root_path.stat().st_size
assert replay['trust_cache_sha256'] == digest(args.trust)
service_configs = media.get('services')
if service_configs is None:
    original_media = load(dev / 'build/root-media/system-launch-services-u12.json')
    assert media['source_sha256'] == original_media['sha256']
    service_configs = original_media['services']
panic = load(run / 'panic.json') if (run / 'panic.json').exists() else None
inputs = [kernel_dir / 'kernel.prelinked.experimental.macho', root_path,
          dev / 'build/root-media/host-data-u11b.apfs',
          args.trust]
record = {
    'updated_at': datetime.now().astimezone().isoformat(),
    'workspace_root': str(root), 'scope': 'Host QEMU only; not SM8350 qualification',
    'target_os': 'iOS 16.5 / 20F66',
    'device_commands_executed': False, 'new_phone_boot_image_created': False,
    'desktop_verified': False, 'physical_display_verified': False,
    'native_touch_verified': False, 'a660_metal_verified': False,
    'launchd_main_verified': 'Early boot complete. Continuing system boot.' in user_log,
    'service_processes_spawned': spawned,
    'springboard_process_spawn_verified': any(name.startswith('SpringBoard[') for name in spawned),
    'backboardd_process_spawn_verified': any(name.startswith('backboardd[') for name in spawned),
    'service_latest_states': service_states,
    'service_spawn_failures': failures,
    'service_exit_reasons': exit_reasons,
    'signature_rejections': signature_rejections,
    'objc_trampoline_missing_error_present': "couldn't dlopen libobjc-trampolines.dylib" in user_log,
    'writable_data_mount_verified': True, 'data_runtime': data,
    'data_mountpoint': '/private/var', 'data_provider': 'NativeRamBlock -> original IOStorageFamily -> original APFS',
    'data_volatile': True, 'persistent_ufs_provider_compiled': False,
    'system_root_readonly': True, 'original_kext_texts_preserved': len(audit['original_executable_kexts_byte_identical']),
    'prelink_pointers_checked': audit['actual_pointer_values_checked'],
    'storage_virtual_slots_checked': abi['method_slots'],
    'storage_compiled_class_bytes': abi['compiled_public_class_size'],
    'existing_file_payloads_preserved': media['existing_file_payloads_preserved'],
    'original_service_configs_restored': len(service_configs),
    'trace_mode': replay.get('syscall_trace_mode', 'all'),
    'syscalls_captured': len(calls), 'panic': panic,
    'replay': relative(run / 'verification.json'), 'syscalls': relative(run / 'syscalls.json'),
    'static_storage_audit': relative(dev / 'build/native-kernel/odin-storage-abi-u12/interface-static-audit.json'),
    'inputs': [{'path': relative(path), 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in inputs],
    'remaining': [
        'Publish an actual version-qualified native display provider; SpringBoard SIGTRAP needs main CADisplay',
        'Complete SpringBoard initialization and verify an actual rendered desktop',
        'Physical PE_init_platform / iOS16.5 PMGR and >2.48GB reserved root handoff',
        'Native MIX4 MobileFramebuffer, ST HID and A660 Metal integration',
    ],
}
if args.service_run == 'u13cryptex':
    assertion_path = out / 'u13-display-assertion.json'
    assertion = load(assertion_path)
    assert assertion['kernel_sha256'] == replay['kernel_sha256']
    record['display_assertion_evidence'] = relative(assertion_path)
    record['static_original_assertion_qualified_by_observed_brk'] = assertion['static_assertion']
(out / 'progress.json').write_text(json.dumps(record, indent=2) + '\n')
status_path = dev / 'migration-status.json'
status = load(status_path)
status.update({
    'updated_at': record['updated_at'],
    'phase': 'Host-only: original APFS writable RAM Data verified; desktop service startup under investigation',
    'host_selected_kernel': relative(kernel_dir / 'kernel.prelinked.experimental.macho').removeprefix('work/UniXNU-odin/'),
    'host_selected_kernel_sha256': replay['kernel_sha256'],
    'host_writable_data_mount_verified': True,
    'host_data_runtime': data,
    'host_service_processes_spawned': spawned,
    'host_springboard_process_spawn_verified': record['springboard_process_spawn_verified'],
    'host_backboardd_process_spawn_verified': record['backboardd_process_spawn_verified'],
    'host_service_latest_states': service_states,
    'host_service_exit_reasons': exit_reasons,
    'host_full_system_root_bytes': root_path.stat().st_size,
    'host_evidence': relative(out / 'progress.json'),
    'host_new_boot_image_created': False, 'latest_host_candidate_device_tested': False,
    'full_ios_desktop_confirmed': False, 'device_commands': False,
    'blockers': record['remaining'],
})
status_path.write_text(json.dumps(status, indent=2) + '\n')
print(json.dumps({k:record[k] for k in ['launchd_main_verified','writable_data_mount_verified',
    'data_runtime','service_processes_spawned','service_spawn_failures','desktop_verified']}, indent=2))
