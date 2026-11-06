"""Package the same u75 kernel with the board-gated GPU offscreen check enabled. No phone commands."""
from pathlib import Path
import subprocess,sys,json,hashlib
D=Path(__file__).resolve().parents[1]
def run(script,*args):
 p=subprocess.run([sys.executable,str(D/'scripts'/script),*args],capture_output=True,text=True)
 print(p.stdout[-1200:],flush=True)
 if p.returncode:raise RuntimeError(p.stderr+p.stdout)
run('build_darwinboot_windows.py','--tag','u76','--desktop-media','--resident-core7','--touch-power')
run('prepare_resident_readback_u70.py','--release','u76','--parent','u75','--kernel',str(D/'build/gpu-port-u75/kernel.prelinked.experimental.macho'))
media=D/'build/device-desktop-u76';cfg=media/'esp/EFI/UniXNU/unixnu.toml'
s=cfg.read_text();needle='odin-touch-bus=1';assert s.count(needle)==1
s=s.replace(needle,needle+' odin-gpu=1 odin-gpu-selftest=1');cfg.write_text(s)
p=media/'manifest.json';m=json.loads(p.read_text())
for item in m['files']:
 q=media/item['path']
 if q==cfg:item.update(sha256=hashlib.sha256(q.read_bytes()).hexdigest(),bytes=q.stat().st_size)
m.update(change='Same u75 HID fix and native kernel; enable SM8350/A660 offscreen GPU pixel validation. Original CPU desktop remains the presentation path.',gpu_hardware_verified=False,desktop_metal_rendering_verified=False)
p.write_text(json.dumps(m,indent=2)+'\n')
run('build_odin_remote_media.py','--tag','u76','--media-tag','u76','--resident-core7','--kernel-readback')
run('check_odin_remote_media.py','--tag','u76','--resident-core7')
run('check_kernel_readback.py','--tag','u76')
run('build_odin_unixnu_bds.py','--remote-media','--tag','u76','--remote-tag','u76','--resident-core7','--kernel-readback')
run('assemble_odin_unixnu_firmware.py','--remote-media-bds','--tag','u76','--darwin-tag','u76','--bds-tag','u76')
run('package_device_desktop_u64.py','--release','u76','--native-proof',str(D/'build/qemu-early-entry-u75core7verified/verification.json'))
