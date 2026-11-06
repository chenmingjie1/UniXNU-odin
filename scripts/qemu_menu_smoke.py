"""Boot the actual freshly built UniXNU manager on an isolated AArch64 VM."""
from pathlib import Path
import json,subprocess,shutil,time,socket,hashlib
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'work/UniXNU-odin/build/qemu-menu';out.mkdir(parents=True,exist_ok=True)
esp=out/'esp';(esp/'EFI/BOOT').mkdir(parents=True,exist_ok=True);(esp/'EFI/UniXNU').mkdir(parents=True,exist_ok=True)
src=ROOT/'work/UniXNU-odin/build/unixnu-efi/UniXNU.efi'
shutil.copy2(src,esp/'EFI/BOOT/BOOTAA64.EFI')
(esp/'EFI/UniXNU/unixnu.toml').write_text('''version = 1
[boot]
timeout = 0
[ui]
title = "MIX 4 UniXNU bring-up"
[kits]
autoload = false
[[entry]]
id = "tools"
title = "Firmware tools"
type = "action"
action = "tools"
''')
qemu=ROOT/'work/odin-portable-linux/qemu'
shutil.copy2(qemu/'share/edk2-arm-vars.fd',out/'vars.fd')
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
cmd=[qemu/'qemu-system-aarch64.exe','-machine','virt','-accel','tcg','-cpu','cortex-a72','-m','512','-smp','1',
 '-display','none','-device','ramfb','-device','qemu-xhci','-device','usb-kbd','-net','none',
 '-drive','if=pflash,format=raw,unit=0,readonly=on,file='+str(qemu/'share/edk2-aarch64-code.fd'),
 '-drive','if=pflash,format=raw,unit=1,file='+str(out/'vars.fd'),
 '-drive','format=raw,readonly=on,file=fat:ro:'+esp.as_posix(),'-serial','file:'+str(out/'serial.log'),
 '-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off','-no-reboot']
(out/'command.json').write_text(json.dumps(list(map(str,cmd)),indent=2)+'\n')
found=False
with (out/'qemu.log').open('wb') as log:
 p=subprocess.Popen(list(map(str,cmd)),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  end=time.monotonic()+55
  while time.monotonic()<end and p.poll() is None:
   time.sleep(.3)
   text=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
   if 'menu: shown' in text:
    found=True;break
  if found:
   with socket.create_connection(('127.0.0.1',port),timeout=5) as s:
    f=s.makefile('rwb');f.readline()
    def qmp(name,**kwargs):
     f.write((json.dumps({'execute':name,'arguments':kwargs})+'\n').encode());f.flush()
     while True:
      obj=json.loads(f.readline())
      if 'return' in obj or 'error' in obj:return obj
    qmp('qmp_capabilities');time.sleep(.5)
    result=qmp('screendump',filename=str(out/'menu.ppm'))
    (out/'screenshot-result.json').write_text(json.dumps(result)+'\n')
 finally:
  if p.poll() is None:p.terminate()
  p.wait(timeout=10)
record={'menu_shown':found,'manager_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
 'scope':'QEMU generic UEFI only; no SM8350 device, kernel or iOS runtime validation','device_io':False}
(out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(record);print((out/'qemu.log').read_text(errors='replace')[-1000:])
if not found:raise SystemExit('UniXNU menu marker not reached')
