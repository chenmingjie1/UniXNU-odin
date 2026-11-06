"""Assemble and independently inspect the USB-backed native desktop boot image."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--release',choices=['u64','u65','u69','u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89'],default='u64');parser.add_argument('--native-proof',type=Path,help='Explicit preserved core7 bootstrap verification for this exact kernel');options=parser.parse_args()
tag=options.release
resident=tag in ('u69','u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89')
darwin_tag=tag if resident else 'u63'
remote_tag=tag if resident else 'u64'
media_tag=tag if resident else 'u63'
OUT=ROOT/('outputs/MIX4-UniXNU-desktop-'+tag);OUT.mkdir(exist_ok=True)
FW=DEV/('build/firmware-'+tag);fd=FW/'UniXNU-odin.fd'
report=json.loads((FW/'verification.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(fd)==report['firmware_sha256'] and report['remote_media']
inspection=DEV/'build/image-inspection'/(tag+'-'+sha(fd)[:16]+'.fd')
inspection.write_bytes(fd.read_bytes());dump=Path(str(inspection)+'.dump')
if not dump.exists():
 r=subprocess.run([str(ROOT/'work/toolchains/uefiextract/UEFIExtract.exe'),str(inspection),'all'],capture_output=True,text=True)
 assert not r.returncode,r.stdout+r.stderr
files={}
for p in dump.rglob('info.txt'):
 m=re.search(r'^File GUID: ([A-F0-9-]+)$',p.read_text(),re.M)
 if m:files[m[1]]=p.parent
for item in report['retained_exact_files']:
 p=files[item['guid']];raw=(p/'header.bin').read_bytes()+(p/'body.bin').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==item['sha256']
assert len(report['retained_exact_files'])==141
assert all(g not in files for g in report['excluded_legacy_apps'])
modules={
 '9B665204-A133-47A2-9396-9E2B370A4E25':DEV/'build/unixnu-efi/UniXNU.efi',
 report['darwinboot_guid']:DEV/('build/darwinboot-'+darwin_tag+'/DarwinBoot.efi'),
 '6D33944A-EC75-4855-A54D-809C75241F6C':DEV/('build/odin-unixnu-bds-'+tag+'/BdsDxe.efi' if tag in ('u65','u69','u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89') else 'build/odin-unixnu-bds/BdsDxe.efi')}
if tag=='u64':modules['ABEE649A-4B85-4776-8350-6464504D4544']=DEV/'build/remote-media-u64/OdinRemoteMedia.efi'
for guid,path in modules.items():
 raw=next(files[guid].glob('* PE32 image section/body.bin')).read_bytes()
 assert raw==path.read_bytes(),str(path)
rpmh=next(files['CB29F4D1-7F37-4692-A416-93E82E219766'].glob('* PE32 image section/body.bin'))
assert sha(rpmh)==report['mmcx_hold_provider_sha256']
shim=DEV/'build/prelinked-payload-u08/BootShim.bin'
assert shim.stat().st_size==112 and struct.unpack_from('<QQ',shim.read_bytes(),8)==(0x9fd00000,0x200000)
kernel=OUT/'uefi-kernel.bin';kernel.write_bytes(shim.read_bytes()+fd.read_bytes())
image=OUT/('MIX4-UniXNU-desktop-'+tag+'-boot.img')
cmd=[sys.executable,str(ROOT/'work/Mu-Silicium-odin/Resources/Scripts/mkbootimg.py'),
     '--header_version','3','--kernel',str(kernel),'-o',str(image)]
r=subprocess.run(cmd,capture_output=True,text=True);assert not r.returncode,r.stdout+r.stderr
raw=image.read_bytes();assert raw[:8]==b'ANDROID!'
assert struct.unpack_from('<I',raw,40)[0]==3
ks,rs=struct.unpack_from('<II',raw,8);assert ks==kernel.stat().st_size and rs==0
assert raw[4096:4096+ks]==kernel.read_bytes()
checks=json.loads((DEV/('build/remote-media-'+remote_tag+'/check/verification.json')).read_text());assert checks['passed']
assert checks['production_source_sha256']==json.loads((DEV/('build/remote-media-'+remote_tag+'/verification.json')).read_text())['source_sha256']
manifest={'schema':1,'artifact':image.name,'bytes':len(raw),'sha256':sha(image),
 'device':'odin','serial':'9bd99408','remote_serial':'odin-unixnu-u64','os':'iOS16.5/20F66',
 'kind':'Physical UniXNU desktop candidate with read-only USB-backed media',
 'boot_header':3,'firmware_sha256':sha(fd),'firmware_modules_readback':{g:sha(p) for g,p in modules.items()},
 'retained_exact_firmware_files':141,'mmcx_hold_provider_sha256':sha(rpmh),
 'kernel_sha256':sha(DEV/('build/device-desktop-'+media_tag+'/esp/EFI/UniXNU/Payloads/kernel.macho')),
 'system_supplied_over_usb':True,'data_supplied_over_usb':True,'requires_host_media_server':True,
 'flash_or_partition_writes':False,'device_tested':False,'physical_desktop_confirmed':False,
 'media_root':str(DEV/('build/device-desktop-'+media_tag)),
 'source_media_manifest':str(DEV/('build/device-desktop-'+media_tag+'/manifest.json')),
 'remote_files':json.loads((DEV/('build/remote-media-'+remote_tag+'/verification.json')).read_text())['files'],
 'checks':checks['checks'],'a660_metal_linked':False,'native_touch_linked':tag in ('u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89'),'native_gpu_linked':tag in ('u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89')}
if resident:
 secondary=json.loads((DEV/'build/resident-secondary-u69/verification.json').read_text());assert secondary['passed']
 native_proof=DEV/('build/qemu-early-entry-'+(tag if tag in ('u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89') else 'u69')+'core7verified/verification.json')
 if options.native_proof:native_proof=options.native_proof.resolve()
 native=json.loads(native_proof.read_text())
 assert native['qemu_resident_secondary'] and native['hardware_breakpoint_reached']
 assert native['kernel_sha256']==manifest['kernel_sha256']
 loader=json.loads((DEV/('build/darwinboot-'+tag+'/verification.json')).read_text());assert loader['resident_core7']
 manifest.update(resident_core7=True,exit_boot_services=False,kernel_cpu_mpidr='0x700',
     firmware_cpu_mpidr='0x0',secondary_entry_computer_check=secondary,
     native_core7_bootstrap_computer_check=str(native_proof),
     physical_resident_usb_verified=False,physical_desktop_confirmed=False)
 if tag in ('u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89'):
  readback=json.loads((DEV/('build/remote-media-'+tag+'/readback-check/verification.json')).read_text());assert readback['passed']
  assert readback['production_header_sha256']==sha(DEV/('build/remote-media-'+tag+'/OdinKernelReadback.h'))
  manifest.update(read_only_kernel_symbols=True,read_only_gop_capture=True,readback_computer_check=readback)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'SHA256SUMS.txt').write_text(manifest['sha256']+'  '+image.name+'\n')
print(json.dumps({k:manifest[k] for k in ('artifact','bytes','sha256','retained_exact_firmware_files','requires_host_media_server')},indent=2))
