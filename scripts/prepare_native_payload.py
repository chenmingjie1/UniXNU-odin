"""Stage the real native kernel and a conservative, measured odin ADT.

This is an early kernel-entry payload. Original iOS kext prelink and an OS
root are deliberately not implied by an executable Mach-O passing audit.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys,tarfile,tomllib,copy
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
UP=ROOT/'work/UniXNU-source/UniXNU-04573c510c5fd4892ca6948739389141cc9e05f5'
sys.path.insert(0,str(UP/'scripts'))
from unixnu.devicetree import generate,read_fdt,registers
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--adt',action='store_true')
parser.add_argument('--kernel',type=Path)
parser.add_argument('--prelink-report',type=Path)
parser.add_argument('--output-dir',type=Path,default=DEV/'build/native-payload')
args=parser.parse_args()
OUT=args.output_dir;OUT.mkdir(parents=True,exist_ok=True)
if args.kernel:
 kernel=args.kernel
else:
 archive=DEV/'build/native-kernel/native-kernel-evidence.tar.gz'
 with tarfile.open(archive) as t:t.extractall(DEV/'build/native-kernel/imported',filter='data')
 kernel=DEV/'build/native-kernel/imported/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped'
prelink=None
if args.prelink_report:
 prelink=json.loads(args.prelink_report.read_text())
 assert prelink['candidate_sha256']==hashlib.sha256(kernel.read_bytes()).hexdigest()
 assert prelink['original_sha256']=='e6fa75598f47b5a9460a60913e2ac8e4cd6cd60eb475bb31da65b68ffbcfdad5'
 assert len(prelink['components'])==30 and len(prelink['original_executable_sha256'])==30
 assert 'com.apple.iokit.IOHIDEventDriver' in prelink['codeless_components']
 (OUT/'prelink-audit.json').write_text(json.dumps(prelink,indent=2)+'\n')
b=kernel.read_bytes();magic,cpu,subtype,kind,ncmd,sz=struct.unpack_from('<6I',b)
assert (magic,cpu,subtype,kind)==(0xfeedfacf,0x100000c,0,2)
pos=32;segments=[];sym=None;deployment=None;entry=None;fips=None
for _ in range(ncmd):
 cmd,length=struct.unpack_from('<II',b,pos);assert length>=8 and pos+length<=32+sz
 if cmd==0x19:
  name,va,vs,off,fs=struct.unpack_from('<16s4Q',b,pos+8);assert off+fs<=len(b)
  segments.append((name.rstrip(b'\0').decode(),va,vs,off,fs))
  for i in range(struct.unpack_from('<I',b,pos+64)[0]):
   section=pos+72+i*80;sname,sg,addr,size,offset=struct.unpack_from('<16s16sQQI',b,section)
   if sname.rstrip(b'\0')==b'__fips_hmacs':fips=(offset,size)
 if cmd==0x2:sym=struct.unpack_from('<4I',b,pos+8)
 if cmd==0x32:deployment=struct.unpack_from('<II',b,pos+8)
 if cmd==5:entry=struct.unpack_from('<Q',b,pos+272)[0]
 pos+=length
assert pos==32+sz and deployment==(2,0x100500) and entry
assert any(va<=entry<va+fs for _,va,_,_,fs in segments)
assert sym and fips and fips[1]==32 and any(b[fips[0]:fips[0]+32])
off,count,stroff,strsize=sym;names={};undefined=[]
for i in range(count):
 index,t,s,d,val=struct.unpack_from('<IBBHQ',b,off+i*16)
 if index>=strsize:raise ValueError('Invalid symbol string offset')
 name=b[stroff+index:b.index(b'\0',stroff+index)].decode(errors='replace')
 if t&0xe==0 and t&1:undefined.append(name)
 if t&0xe==0xe:names[name]=val
assert not undefined,undefined
required=['_source_corecrypto14_bootstrap','_source_pthread_bootstrap','_corecrypto_kext_start','_pthread_start',
 '__ZN6ArmCpu5startEP9IOService','__ZN13ArmDTPlatform9configureEP9IOService']
# Namespace-qualified C++ manglings vary with the class/method signature.
assert all(x in names for x in required[:4])
assert any('ArmDTPlatform' in x and 'configure' in x for x in names)
assert any('ArmCpu' in x and 'start' in x for x in names)
tcraddr=names['_sysreg_restore'];tcr=None
for _,va,_,fo,fs in segments:
 if va<=tcraddr<tcraddr+8<=va+fs:tcr=struct.unpack_from('<Q',b,fo+tcraddr-va)[0]
assert tcr is not None and (tcr>>14)&3==0 and (tcr>>30)&3==2
(OUT/'kernel-audit.json').write_text(json.dumps({'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),
 'undefined_external_symbols':undefined,'deployment':'iOS 16.5','source_version':'8796.101.5',
 'entry_va':hex(entry),'initial_tcr':hex(tcr),'page_bytes':4096,'crypto_hmac_present':True,
 'source_crypto_and_pthread_bootstraps_linked':True,'platform_and_cpu_linked':True,
 'runtime_crypto_selftests_executed':False,'original_kexts_prelinked':prelink is not None,
 'original_executable_kext_count':len(prelink['components']) if prelink else 0,
 'prelink_runtime_qualified':False},indent=2)+'\n')
hardware=ROOT/'outputs/MIX4-odin-porting/android-display-baseline/20261027-161736/live.dtb'
tree=read_fdt(hardware.read_bytes());memory=next(x for x in tree.children if x.name=='memory')
banks=registers(memory);high=next((base,size) for base,size in banks if base==0x200000000)
assert high==(0x200000000,0x180000000)
gic=next(x for x in tree.walk() if x.name=='interrupt-controller@17a00000')
assert registers(gic)==[(0x17a00000,0x10000),(0x17a60000,0x100000)]
assert gic.scalar('#interrupt-cells')==3
# The ADT generator requires one DRAM bank. Use only a measured contiguous
# bank, not a fictitious range spanning firmware/peripheral reservations.
dts='''/dts-v1/;
/include/ "sm8350.dtsi"
/ {
 model = "Xiaomi MIX 4";
 compatible = "xiaomi,odin", "qcom,sm8350";
 memory@200000000 { device_type = "memory"; reg = <2 0 1 0x80000000>; };
};
&cpu1 { status = "disabled"; };
&cpu2 { status = "disabled"; };
&cpu3 { status = "disabled"; };
&cpu4 { status = "disabled"; };
&cpu5 { status = "disabled"; };
&cpu6 { status = "disabled"; };
&cpu7 { status = "disabled"; };
'''
(OUT/'odin-entry.dts').write_text(dts)
# Compilation to DTB is done by the actual Linux dtc, then this script is
# called with --adt to generate the Apple sidecar from the resulting file.
esp=OUT/'esp/EFI/UniXNU';(esp/'Payloads').mkdir(parents=True,exist_ok=True)
(esp/'Payloads/kernel.macho').write_bytes(b)
import shutil
shutil.copy2(DEV/'build/darwinboot/DarwinBoot.efi',esp/'DarwinBoot.efi')
(esp/'unixnu.toml').write_text('''version = 1
[boot]
timeout = 10
fallback_timeout = -1
default = "xnu-core"
[ui]
title = "MIX 4 - UniXNU kernel bring-up"
[kits]
autoload = false
[[entry]]
id = "xnu-core"
title = "XNU 8796 core test (no iOS desktop)"
type = "xnu"
path = "Payloads/kernel.macho"
args = "-v serial=0 cpus=1"
[[entry]]
id = "tools"
title = "Firmware tools"
type = "action"
action = "tools"
[[entry]]
id = "reset"
title = "Restart phone"
type = "action"
action = "reset"
''')
if '--adt' in sys.argv:
 profile=tomllib.loads((UP/'profiles/os/ios-16.5-20F66/profile.toml').read_text())
 profile.setdefault('payload',{})['adt']={'owned_memory_size':'0x20000000'}
 adt=generate(OUT/'odin-entry.dtb',profile)
 (esp/'Payloads/kernel.macho.adt').write_bytes(adt)
(OUT/'hardware-evidence.json').write_text(json.dumps({'source_fdt':str(hardware),
 'sha256':hashlib.sha256(hardware.read_bytes()).hexdigest(),'dram_bank_subset':list(high),
 'all_measured_banks':banks,'measured_gic_resources':registers(gic),'measured_interrupt_cells':3,
 'boot_cpu_affinity':'0x0','single_cpu_only':True,
 'allocation_policy':'DarwinBoot must obtain its complete 512 MiB window from actual conventional memory',
 'device_qualified':False,'ios_root_included':False,'native_hid_worker_linked':False,'a660_metal_linked':False},indent=2)+'\n')
print('Native kernel audited and staged',len(b),'bytes; ADT', '--adt' in sys.argv)
