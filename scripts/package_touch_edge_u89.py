"""Package the u89 edge-metadata candidate with unchanged u88 RAM userland."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

D = Path(__file__).resolve().parents[1]


def run(script, *args):
    subprocess.run([sys.executable, str(D / 'scripts' / script), *args], check=True)


def main():
    proof = D / 'build/qemu-early-entry-u89core7verified/verification.json'
    p = json.loads(proof.read_text())
    kernel = D / 'build/touch-edge-u89/kernel.prelinked.experimental.macho'
    assert p['kernel_sha256'] == hashlib.sha256(kernel.read_bytes()).hexdigest()
    assert p['qemu_resident_secondary'] and p['hardware_breakpoint_reached']
    run('build_darwinboot_windows.py', '--tag', 'u89', '--desktop-media', '--resident-core7', '--touch-power')
    run('prepare_resident_readback_u70.py', '--release', 'u89', '--parent', 'u88', '--kernel', str(kernel))
    media = D / 'build/device-desktop-u89'
    cfg = media / 'esp/EFI/UniXNU/unixnu.toml'
    source = cfg.read_text()
    assert source.count('odin-touch-bus=1') == 1 and 'odin-touch-edge=' not in source
    cfg.write_text(source.replace('odin-touch-bus=1', 'odin-touch-bus=1 odin-touch-edge=1'))
    path = media / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest.update(change='u88 System/Data/UI idle assertion unchanged; exact 20F66 edge-contact metadata for Home gesture',
                    edge_gesture_device_verified=False, latency_fixed=False,
                    desktop_gpu_composition_verified=False)
    for item in manifest['files']:
        file = media / item['path']
        item.update(sha256=hashlib.sha256(file.read_bytes()).hexdigest(), bytes=file.stat().st_size)
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    run('build_odin_remote_media.py', '--tag', 'u89', '--media-tag', 'u89', '--resident-core7', '--kernel-readback')
    run('check_kernel_readback.py', '--tag', 'u89')
    run('check_odin_remote_media.py', '--tag', 'u89', '--resident-core7')
    run('build_odin_unixnu_bds.py', '--remote-media', '--tag', 'u89', '--remote-tag', 'u89', '--resident-core7', '--kernel-readback')
    run('assemble_odin_unixnu_firmware.py', '--remote-media-bds', '--tag', 'u89', '--darwin-tag', 'u89', '--bds-tag', 'u89')
    run('package_device_desktop_u64.py', '--release', 'u89', '--native-proof', str(proof))


if __name__ == '__main__':
    main()
