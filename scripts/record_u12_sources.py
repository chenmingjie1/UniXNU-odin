"""Bind exported source evidence to the actual audited host runtime kernel."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
out = root / 'outputs/MIX4-UniXNU-host-u12'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


archive = out / 'odin-host-u12-final-source.tar.gz'
assert digest(archive) == 'd81d6f5f71ff5a3e03f0722010d2e2e1a897fdb624318d04f0951ac6adfd7cef'
names = ['odin-host-data.patch', 'odin-data-preflight.patch', 'odin-ram-data-provider.patch']
series = (dev / 'patches/xnu/series').read_text().splitlines()
assert series[-3:] == names
link = dev / 'scripts/link_offline_kernel.sh'
text = link.read_text()
assert 'ram-block/libRamBlock.a' in text
assert 'KernelConfigTables.cpo_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1' in text
assert '-DXNU_OWNER_DATA_MOUNT=1 -DXNU_OWNER_BOOT_MANIFEST=1 -DXNU_NATIVE_RAM_BLOCK=1' in text
kernel = dev / 'build/ios16-prelink-u12match/kernel.prelinked.experimental.macho'
assert digest(kernel) == '0921dad787ce8e41272bdef6e04ed6cb38eb9bc943c677ff4cadf0fe46278591'
paths = [archive, kernel, link, dev / 'patches/xnu/series']
paths += [dev / 'patches/xnu' / name for name in names]
paths += [dev / 'scripts' / name for name in [
    'install_odin_host_data.py', 'install_odin_data_preflight.py',
    'install_odin_ram_data_provider.py', 'prepare_odin_ram_block.py',
    'compile_odin_storage_reference.py', 'build_odin_ram_block.py',
    'audit_odin_storage_abi.py', 'bind_odin_ram_block.py',
    'qemu_early_entry.py', 'prepare_launch_services_root.py',
    'finalize_u12_host_progress.py', 'run_u12_host_services.ps1',
    'prepare_u13_service_trust.py', 'restore_cryptex_trampolines.py',
    'symbolicate_u13_display_assertion.py',
]]
receipt = {
    'scope': 'Computer-only source export; not a phone image',
    'selected_runtime_kernel_sha256': digest(kernel),
    'patch_order_appended': names,
    'archive_includes_later_warning_checks': True,
    'later_warning_checks_do_not_imply_runtime_kernel_relinked': True,
    'device_commands_executed': False,
    'files': [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
               'sha256': digest(p)} for p in paths],
}
(out / 'source-evidence.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('Saved source hashes, patch order and selected runtime kernel identity')
