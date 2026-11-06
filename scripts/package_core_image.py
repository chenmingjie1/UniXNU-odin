"""Assemble and independently inspect the odin v3 RAM-boot candidate.

No adb, fastboot, partition writes or device commands are used here.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess,sys,tomllib
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release',default='u01')
parser.add_argument('--payload-dir',type=Path,default=DEV/'build/native-payload')
args=parser.parse_args()
version=args.release
assert re.fullmatch(r'u[0-9]{2,4}',version)
OUT=ROOT/('outputs/MIX4-UniXNU-core-'+version);OUT.mkdir(parents=True,exist_ok=True)
BUILD=DEV/'build';PAY=args.payload_dir
sha=lambda b:hashlib.sha256(b).hexdigest()
readjson=lambda p:json.loads(p.read_text())
def run(cmd):
 p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr
 return p.stdout+p.stderr

# Extract the final FD afresh under a content-addressed path. Do not trust
# the build's staging FFS inventory as proof of what reached the image.
fd=(BUILD/'firmware/UniXNU-odin.fd').read_bytes();assert len(fd)==0x200000
inspection=BUILD/'image-inspection';inspection.mkdir(exist_ok=True)
fdpath=inspection/(sha(fd)[:16]+'.fd');fdpath.write_bytes(fd)
dump=Path(str(fdpath)+'.dump')
if not dump.exists():
 log=run([ROOT/'work/toolchains/uefiextract/UEFIExtract.exe',fdpath,'all'])
 (inspection/(fdpath.stem+'-extract.log')).write_text(log)
files={}
for p in dump.rglob('info.txt'):
 m=re.search(r'^File GUID: ([A-F0-9-]+)$',p.read_text(),re.M)
 if m:
  assert m[1] not in files,m[1]
  files[m[1]]=p.parent
fw=readjson(BUILD/'firmware/verification.json');assert fw['firmware_sha256']==sha(fd)
retained=[]
for item in fw['retained_exact_files']:
 p=files[item['guid']];raw=(p/'header.bin').read_bytes()+(p/'body.bin').read_bytes()
 assert sha(raw)==item['sha256'],item['guid']
 retained.append(item['guid'])
assert len(retained)==141
assert all(g not in files for g in fw['excluded_legacy_apps'])
modules={
 '9B665204-A133-47A2-9396-9E2B370A4E25':'unixnu-efi/UniXNU.efi',
 fw['darwinboot_guid']:'darwinboot/DarwinBoot.efi',
 '75CA63AD-FBAE-4A06-92A0-F937C671251D':'UniXNURamDiskDxe/UniXNURamDiskDxe.efi',
 '29B950CF-586D-49EA-9D71-F88645CCDAF6':'UniXNUDxe/UniXNUDxe.efi',
 '6D33944A-EC75-4855-A54D-809C75241F6C':'odin-unixnu-bds/BdsDxe.efi'}
checked={}
for guid,source in modules.items():
 pe=next(files[guid].glob('* PE32 image section/body.bin')).read_bytes()
 assert pe==(BUILD/source).read_bytes(),source
 checked[guid]={'source':source,'sha256':sha(pe)}
rpmh=next(files['CB29F4D1-7F37-4692-A416-93E82E219766'].glob('* PE32 image section/body.bin')).read_bytes()
assert sha(rpmh)==fw['mmcx_hold_provider_sha256']
sec=next(files['9AFFB503-E643-4141-8B90-17E8588B1D35'].glob('* TE image section/body.bin')).read_bytes()
assert sec==(BUILD/'odin-unixnu-sec/Sec.te').read_bytes()
sig,machine,nsec,subsystem,stripped,entry,code,base=struct.unpack_from('<HHBBHIIQ',sec)
assert (sig,machine,base)==(0x5a56,0xaa64,0x9fd00000)
assert 0<=entry+40-stripped<len(sec)
# FV's ARM reset vector must branch to the in-place SEC entry.
vector=struct.unpack_from('<I',fd)[0];assert vector&0xfc000000==0x14000000
imm=vector&0x3ffffff
if imm&0x2000000:imm-=0x4000000
target=imm*4;assert target==entry and target==0x1000
assert fd[target:target+4]==sec[entry+40-stripped:entry+44-stripped]
assert fd[target:target+4]==bytes.fromhex('fc0300aa') # mov x28,x0, FDT preservation
abi=readjson(BUILD/'boot-abi/verification.json');assert abi['passed'] and abi['command_line_bytes']==608
assert abi['darwinboot_header_sha256']==sha((BUILD/'darwinboot/source/BootArgs.h').read_bytes())
prefix=readjson(BUILD/'initrd-prefix-test/verification.json');assert prefix['passed'] and prefix['cases']>=16
assert prefix['driver_source_sha256']==sha((BUILD/'UniXNURamDiskDxe/UniXNURamDiskDxe-odin.c').read_bytes())

# Independently decode the generated ADT and verify its effective resources.
adt=(PAY/'esp/EFI/UniXNU/Payloads/kernel.macho.adt').read_bytes();nodes={}
def node(pos,parent=''):
 np,nc=struct.unpack_from('<II',adt,pos);pos+=8;props={}
 assert np<512 and nc<512
 for _ in range(np):
  name,size=struct.unpack_from('<32sI',adt,pos);pos+=36
  name=name.rstrip(b'\0').decode();assert pos+size<=len(adt)
  assert name not in props
  props[name]=adt[pos:pos+size];pos+=(size+3)&~3
 name=props['name'].rstrip(b'\0').decode();path=parent+'/'+name
 assert path not in nodes;nodes[path]=props
 for _ in range(nc):pos=node(pos,path)
 return pos
assert node(0)==len(adt)
chosen=nodes['/device-tree/chosen']
u64=lambda b:struct.unpack('<Q',b)[0]
assert (u64(chosen['dram-base']),u64(chosen['dram-size']))==(0x200000000,0x180000000)
assert u64(chosen['darwinboot-memory-size'])==0x20000000
cpus=[p for p in nodes if p.startswith('/device-tree/cpus/cpu')]
assert cpus==['/device-tree/cpus/cpu0']
assert struct.unpack('<I',nodes[cpus[0]]['reg'])[0]==0
assert struct.unpack('<I',nodes[cpus[0]]['timebase-frequency'])[0]==19200000
assert len(chosen['nvram-proxy-data'])==8192
assert nodes['/device-tree']['model']==b'iPhone10,3\0'
assert b'xiaomi,odin\0' in nodes['/device-tree']['compatible']
_,io_base,io_size=struct.unpack('<QQQ',nodes['/device-tree/arm-io']['ranges'])
gic=struct.unpack('<4Q',nodes['/device-tree/arm-io/intc']['reg'])
assert (io_base+gic[0],gic[1],io_base+gic[2],gic[3])==(0x17a00000,0x10000,0x17a60000,0x100000)
cfg=tomllib.loads((PAY/'esp/EFI/UniXNU/unixnu.toml').read_text())
assert cfg['boot']['timeout']==10 and cfg['boot']['default']=='xnu-core'
fat=(PAY/'payload.fat').read_bytes();fatrecord=readjson(PAY/'fat-verification.json')
assert sha(fat)==fatrecord['sha256'] and fatrecord['all_payload_files_readback_equal']
for item in fatrecord['files']:
 b=(PAY/'esp'/item['path']).read_bytes();assert len(b)==item['bytes'] and sha(b)==item['sha256']

# This is the measured odin format: uncompressed 112-byte ARM64 shim + FD,
# Android header v3, and a FAT ramdisk. Not the upstream gzip/header0 recipe.
shim=(PAY/'BootShim.bin').read_bytes();assert len(shim)==112
assert struct.unpack_from('<QQ',shim,8)==(0x9fd00000,0x200000)
assert shim[56:60]==b'ARM\x64'
kernel=shim+fd;(OUT/'uefi-kernel.bin').write_bytes(kernel)
image=OUT/('MIX4-UniXNU-iOS16.5-core-'+version+'-boot.img')
cmd=[sys.executable,ROOT/'work/Mu-Silicium-odin/Resources/Scripts/mkbootimg.py','--header_version','3',
 '--kernel',OUT/'uefi-kernel.bin','--ramdisk',PAY/'payload.fat','-o',image]
run(cmd)
b=image.read_bytes();assert b[:8]==b'ANDROID!'
ksize,rsize,osver,hsize=struct.unpack_from('<4I',b,8)
assert (ksize,rsize,osver,hsize)==(len(kernel),len(fat),0,1580)
assert struct.unpack_from('<I',b,40)[0]==3
align=lambda n:(n+4095)&~4095
ramoff=4096+align(ksize)
assert b[4096:4096+ksize]==kernel and b[ramoff:ramoff+rsize]==fat
assert len(b)==ramoff+align(rsize)
assert b[44:1580]==bytes(1536)
audit=readjson(PAY/'kernel-audit.json')
has_prelink=audit['original_kexts_prelinked']
prelink_audit=readjson(PAY/'prelink-audit.json') if has_prelink else None
if has_prelink:
 assert prelink_audit['candidate_sha256']==sha((PAY/'esp/EFI/UniXNU/Payloads/kernel.macho').read_bytes())
 assert len(prelink_audit['original_executable_sha256'])==30
 prelink_audit={key:prelink_audit[key] for key in (
  'native_sha256','original_sha256','candidate_sha256','candidate_bytes','slide',
  'components','codeless_components','pointer_counts','original_executable_sha256',
  'source_inputs_modified','runtime_qualified','abi_qualified','loadable')}
 prelink_audit['full_report_sha256']=sha((PAY/'prelink-audit.json').read_bytes())
report={
 'artifact':image.name,'bytes':len(b),'sha256':sha(b),'kind':'early native XNU core RAM-boot candidate',
 'target_device':'Xiaomi MIX 4 / odin / SM8350','target_os_abi':'iOS 16.5 / 20F66',
 'device_tested':False,'complete_ios_system':False,'ios_desktop_expected':False,
 'original_kexts_prelinked':has_prelink,'native_touch_driver_linked':False,'a660_metal_linked':False,
 'touch_latency_or_display_flicker_fixed':False,'device_commands_executed':False,
 'boot_header_version':3,'kernel_offset':4096,'kernel_bytes':ksize,'kernel_sha256':sha(kernel),
 'ramdisk_offset':ramoff,'ramdisk_bytes':rsize,'ramdisk_sha256':sha(fat),
 'firmware_sha256':sha(fd),'shim_sha256':sha(shim),'retained_exact_ffs_count':len(retained),
 'mmcx_hold_provider_sha256':sha(rpmh),'new_modules_readback':checked,
 'sec_image_base':hex(base),'sec_entry_offset':hex(target),'sec_preserves_fdt_x0':True,
 'boot_args_structure_bytes':abi['structure_bytes'],'boot_args_fields_match_actual_kernel':True,
 'initrd_prefix_cases_passed':prefix['cases'],'fat_payload_files_readback':fatrecord['files'],
 'adt':{'sha256':sha(adt),'single_cpu_affinity':0,'dram_base':hex(0x200000000),
        'dram_size':hex(0x180000000),'darwinboot_owned_bytes':0x20000000,
        'gicd':hex(0x17a00000),'gicd_bytes':0x10000,'gicr':hex(0x17a60000),
        'gicr_bytes':0x100000,'hardware_interrupt_cells':3,'nvram_proxy_bytes':8192},
 'kernel_audit':audit,'qemu_menu':readjson(BUILD/'qemu-menu/verification.json'),
 'prelink_audit':prelink_audit,
 'build_command':list(map(str,cmd)),
 'limitations':['No OS root included' if has_prelink else 'No original Apple kext prelink or OS root included',
  'No native IOHID lifecycle/worker or Adreno 660 Metal integration',
  'QEMU evidence covers generic firmware menu only; no odin kernel runtime qualification',
  'Hardware recovery may require a physical long press; this image provides no verified remote recovery channel']}
(OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/'SHA256SUMS.txt').write_text(sha(b)+'  '+image.name+'\n')
(OUT/'README.txt').write_text(('''MIX 4 UniXNU RELEASE — 原生内核入口测试候选

包含：源码编译的 XNU 8796.101.5、UniXNU 菜单、DarwinBoot、MIX 4 固件、设备树。
使用 iOS 16.5 / 20F66 ABI；保留已验证亮屏固件中的 MMCX hold 驱动。
菜单默认倒计时 10 秒后尝试启动内核。

此镜像未在实机运行。不含原始 Apple kext prelink 和 iOS 根文件系统，
不能进入 iOS 桌面；新框架的原生触摸、A660 Metal 和闪烁修复尚未完成。
旧 HakiOS 的触摸、GPU 实测结果不能作为这个镜像的验收结果。

仅作为 RAM 临时启动候选，不写 boot/vendor_boot，不切槽、不清空数据。
本次只在电脑生成和校验镜像，没有操作手机。
实机验证需要恢复手段：若挂起，可能必须现场长按电源恢复 Android。

manifest.json 记录最终镜像结构、各组件 SHA256 及检查范围。
SHA256SUMS.txt 可用于确认传输完整性。
''').replace('RELEASE',version).replace(
 '此镜像未在实机运行。不含原始 Apple kext prelink 和 iOS 根文件系统，',
 '此镜像未在实机运行。已预链接 30 个原始 Apple 驱动及 IOHIDEventDriver 配置条目；不含 iOS 根文件系统，'
 if has_prelink else '此镜像未在实机运行。不含原始 Apple kext prelink 和 iOS 根文件系统，'),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['artifact','bytes','sha256','retained_exact_ffs_count','boot_args_fields_match_actual_kernel','device_tested']},indent=2))
