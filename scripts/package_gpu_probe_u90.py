"""Package u90 bounded original-IOSurface GPU probe; no phone commands."""
from pathlib import Path
import hashlib,json,subprocess,sys

D=Path(__file__).resolve().parents[1]

def run(name,*args):
    subprocess.run([sys.executable,str(D/'scripts'/name),*args],check=True)

def main():
    kernel=D/'build/gpu-probe-u90/kernel.prelinked.experimental.macho'
    proof=D/'build/qemu-early-entry-u90core7verified/verification.json'
    record=json.loads(proof.read_text())
    assert record['qemu_resident_secondary'] and record['hardware_breakpoint_reached']
    assert record['kernel_sha256']==hashlib.sha256(kernel.read_bytes()).hexdigest()
    run('build_darwinboot_windows.py','--tag','u90','--desktop-media','--resident-core7','--touch-power')
    run('prepare_resident_readback_u70.py','--release','u90','--parent','u89','--kernel',str(kernel),
        '--system',str(D/'build/root-media/system-host-input-u90.apfs'),
        '--trust-cache',str(D/'build/root-media/host-input-development-trust-u90.bundle'))
    media=D/'build/device-desktop-u90';path=media/'manifest.json';m=json.loads(path.read_text())
    m.update(change='u89 touch/display preserved; bounded original IOSurface GPU userptr/write/fence/readback probe and UI exit reason observations',
             desktop_gpu_composition_verified=False,physical_surface_import_verified=False,
             gpu_probe_installation='existing signed UI helper, once per process on background queue',
             gpu_probe_panel_present=False,partition_writes=False)
    path.write_text(json.dumps(m,indent=2)+'\n')
    run('build_odin_remote_media.py','--tag','u90','--media-tag','u90','--resident-core7','--kernel-readback')
    run('check_kernel_readback.py','--tag','u90')
    run('check_odin_remote_media.py','--tag','u90','--resident-core7')
    run('build_odin_unixnu_bds.py','--remote-media','--tag','u90','--remote-tag','u90','--resident-core7','--kernel-readback')
    run('assemble_odin_unixnu_firmware.py','--remote-media-bds','--tag','u90','--darwin-tag','u90','--bds-tag','u90')
    run('package_device_desktop_u64.py','--release','u90','--native-proof',str(proof))

if __name__=='__main__':main()
