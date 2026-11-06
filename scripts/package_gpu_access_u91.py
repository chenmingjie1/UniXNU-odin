"""Package the authorized service-scoped u91 experiment; no phone operations."""
from pathlib import Path
import hashlib
import json
from package_gpu_probe_u90 import run

D = Path(__file__).resolve().parents[1]


def main():
    kernel = D / 'build/gpu-access-u91/kernel.prelinked.experimental.macho'
    proof = D / 'build/qemu-early-entry-u91core7verified/verification.json'
    verification = json.loads(proof.read_text())
    assert verification['qemu_resident_secondary'] and verification['hardware_breakpoint_reached']
    assert verification['kernel_sha256'] == hashlib.sha256(kernel.read_bytes()).hexdigest()
    run('build_darwinboot_windows.py', '--tag', 'u91', '--desktop-media', '--resident-core7', '--touch-power')
    run('prepare_resident_readback_u70.py', '--release', 'u91', '--parent', 'u90', '--kernel', str(kernel))
    manifest = D / 'build/device-desktop-u91/manifest.json'
    record = json.loads(manifest.read_text())
    record.update(change='u90 probe retained; explicitly authorized native GPU access for SpringBoard/backboardd',
                  sandbox_exception_service='HakiosGPU',
                  sandbox_exception_processes=['SpringBoard', 'backboardd'],
                  desktop_gpu_composition_verified=False, physical_surface_import_verified=False,
                  gpu_probe_panel_present=False, partition_writes=False)
    manifest.write_text(json.dumps(record, indent=2) + '\n')
    run('build_odin_remote_media.py', '--tag', 'u91', '--media-tag', 'u91', '--resident-core7', '--kernel-readback')
    run('check_kernel_readback.py', '--tag', 'u91')
    run('check_odin_remote_media.py', '--tag', 'u91', '--resident-core7')
    run('build_odin_unixnu_bds.py', '--remote-media', '--tag', 'u91', '--remote-tag', 'u91', '--resident-core7', '--kernel-readback')
    run('assemble_odin_unixnu_firmware.py', '--remote-media-bds', '--tag', 'u91', '--darwin-tag', 'u91', '--bds-tag', 'u91')
    run('package_device_desktop_u64.py', '--release', 'u91', '--native-proof', str(proof))


if __name__ == '__main__':
    main()
