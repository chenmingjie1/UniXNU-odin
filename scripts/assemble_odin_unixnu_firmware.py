"""Build a new FV from the exact previously working MMCX firmware inventory."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,uuid
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
MU=ROOT/'work/Mu-Silicium-odin';BT=MU/'Mu_Basecore/BaseTools/Bin/Mu-Basetools_extdep/Windows-x86'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--remote-media',action='store_true')
parser.add_argument('--remote-media-bds',action='store_true')
parser.add_argument('--tag',default='')
parser.add_argument('--darwin-tag',default='u63')
parser.add_argument('--bds-tag',default='u65')
options=parser.parse_args()
assert not (options.remote_media and options.remote_media_bds)
assert all(not x or x.isalnum() for x in (options.tag,options.darwin_tag,options.bds_tag))
desktop=options.remote_media or options.remote_media_bds
BASEOUT=DEV/'build/firmware'
OUT=DEV/('build/firmware-u65' if options.remote_media_bds else 'build/firmware-u64' if options.remote_media else 'build/firmware')
OUT.mkdir(exist_ok=True)
if options.tag:
 OUT=DEV/('build/firmware-'+options.tag);OUT.mkdir(exist_ok=True)
BASE=BASEOUT/'baseline.fd.dump';commands=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASEOUT/'baseline.fd')=='bbdf0b2b6cbe8b31014d446cc8fa0a7fc5f4f951f5e75a34bc22082f2d9d48be'
def run(args):
 commands.append(list(map(str,args)));p=subprocess.run(args,capture_output=True,text=True)
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 with (OUT/'build.log').open('a') as f:f.write(p.stdout+p.stderr)
 if p.returncode:raise SystemExit((p.stdout+p.stderr)[-4500:])
(OUT/'build.log').write_text('')
files={}
for p in BASE.rglob('info.txt'):
 m=re.search(r'^File GUID: ([A-F0-9-]+)$',p.read_text(),re.M)
 if m:files[m[1]]=p.parent
bds='6D33944A-EC75-4855-A54D-809C75241F6C'
volume=files[bds].parent
ordered=sorted((p for p in files.values() if p.parent==volume),key=lambda p:int(p.name.split()[0]))
ffsdir=OUT/'ffs';ffsdir.mkdir(exist_ok=True);original_hashes={}
def original(path):
 raw=(path/'header.bin').read_bytes()+(path/'body.bin').read_bytes()
 assert len(raw)==int.from_bytes(raw[20:23],'little')
 guid=str(uuid.UUID(bytes_le=raw[:16])).upper();dst=ffsdir/(guid+'.ffs')
 original_hashes[guid]=hashlib.sha256(raw).hexdigest()
 # GenFv complements the input file-state byte for an erase-polarity-1 FV.
 # Inputs extracted from a finished FV already contain that stored polarity.
 # Undo it in staging so the final image preserves the baseline byte exactly.
 staged=bytearray(raw);staged[23]^=0xff;dst.write_bytes(staged)
 return guid,dst
def new(guid,efi,kind='EFI_FV_FILETYPE_DRIVER',depex=b'\x06\x08'):
 pe=ffsdir/(guid+'.pe32');run([BT/'GenSec.exe','-s','EFI_SECTION_PE32','-o',pe,efi])
 args=[BT/'GenFfs.exe','-t',kind,'-g',guid,'-o',ffsdir/(guid+'.ffs')]
 if kind!='EFI_FV_FILETYPE_APPLICATION':
  raw=ffsdir/(guid+'.depex');raw.write_bytes(depex);sec=ffsdir/(guid+'.dpx')
  run([BT/'GenSec.exe','-s','EFI_SECTION_DXE_DEPEX','-o',sec,raw]);args+=['-i',sec]
 run([*args,'-i',pe]);return ffsdir/(guid+'.ffs')
retained=[];excluded=[];paths=[]
for p in ordered:
 guid,path=original(p)
 if guid.startswith('3D8835E5-') or guid in ('D830FE6B-5C48-5139-9890-5E5C9B8A2A5C','CC680C97-94CE-4C09-A377-4BED5E6E9CB9'):
  excluded.append(guid);continue
 if guid==bds:path=new(guid,DEV/('build/odin-unixnu-bds-'+options.bds_tag+'/BdsDxe.efi' if options.remote_media_bds else 'build/odin-unixnu-bds/BdsDxe.efi'),depex=(p/'0 DXE dependency section/body.bin').read_bytes())
 else:retained.append({'guid':guid,'sha256':original_hashes[guid]})
 paths.append(path)
# Preserve the exact MMCX hold provider, rather than substituting stock RPMh.
rpmh=files['CB29F4D1-7F37-4692-A416-93E82E219766']
rpmhpe=next(rpmh.glob('* PE32 image section/body.bin'))
assert sha(rpmhpe)=='186f2adc3be0a6a59b5db243a04661ae327e118e2e3fd2e603f79517db412106'
app='9B665204-A133-47A2-9396-9E2B370A4E25';darwin=''
inf=ROOT/'work/UniXNU-components/DarwinBoot-3c75734014cdab0acd9541e88057b7606ee7ae08/DarwinBootPkg/Driver/DarwinBoot.inf'
darwin=re.search(r'FILE_GUID\s*=\s*([A-Fa-f0-9-]+)',inf.read_text())[1].upper()
paths.append(new(app,DEV/'build/unixnu-efi/UniXNU.efi','EFI_FV_FILETYPE_APPLICATION'))
paths.append(new(darwin,DEV/('build/darwinboot-'+options.darwin_tag+'/DarwinBoot.efi' if desktop else 'build/darwinboot/DarwinBoot.efi')))
if options.remote_media:
 paths.append(new('ABEE649A-4B85-4776-8350-6464504D4544',DEV/'build/remote-media-u64/OdinRemoteMedia.efi'))
paths.append(new('75CA63AD-FBAE-4A06-92A0-F937C671251D',DEV/'build/UniXNURamDiskDxe/UniXNURamDiskDxe.efi'))
dec=(MU/'Mu_Basecore/MdePkg/MdePkg.dec').read_text()
def guidbytes(name):
 s=re.search(r'^\s*'+name+r'\s*=\s*\{([^\n]+)\}',dec,re.M)[1]
 values=[int(x,16) for x in re.findall(r'0x([a-fA-F0-9]+)',s)]
 return struct.pack('<IHH8B',*values)
dependency=b'\x02'+guidbytes('gEfiVariableArchProtocolGuid')+b'\x02'+guidbytes('gEfiVariableWriteArchProtocolGuid')+b'\x03\x08'
paths.append(new('29B950CF-586D-49EA-9D71-F88645CCDAF6',DEV/'build/UniXNUDxe/UniXNUDxe.efi',depex=dependency))
template=(MU/'Build/odinPkg/RELEASE_CLANGPDB/FV/FVMAIN.inf').read_text().split('[files]')[0]
maininf=OUT/'FVMAIN.inf';maininf.write_text(template+'[files]\n'+''.join('EFI_FILE_NAME = '+str(p)+'\n' for p in paths))
run([BT/'GenFv.exe','-i',maininf,'-o',OUT/'FVMAIN.Fv'])
run([BT/'GenSec.exe','-s','EFI_SECTION_FIRMWARE_VOLUME_IMAGE','-o',OUT/'main.sec',OUT/'FVMAIN.Fv'])
run([BT/'GenSec.exe','--sectionalign','8','-o',OUT/'main.aligned',OUT/'main.sec'])
run([BT/'LzmaCompress.exe','-e','-o',OUT/'main.lzma',OUT/'main.aligned'])
run([BT/'GenSec.exe','-s','EFI_SECTION_GUID_DEFINED','-g','EE4E5898-3914-4259-9D6E-DC7BD79403CF','-r','PROCESSING_REQUIRED','-o',OUT/'main.guided',OUT/'main.lzma'])
compact=OUT/'main.ffs'
run([BT/'GenFfs.exe','-t','EFI_FV_FILETYPE_FIRMWARE_VOLUME_IMAGE','-g','9E21FD93-9C72-4c15-8C4B-E77F1DB2D792','-o',compact,'-i',OUT/'main.guided'])
guid='9AFFB503-E643-4141-8B90-17E8588B1D35'
run([BT/'GenSec.exe','-s','EFI_SECTION_TE','-o',OUT/'sec.section',DEV/'build/odin-unixnu-sec/Sec.te'])
secffs=ffsdir/(guid+'.ffs')
run([BT/'GenFfs.exe','-t','EFI_FV_FILETYPE_SECURITY_CORE','-g',guid,'-x','-o',secffs,'-i',OUT/'sec.section','-n','0'])
template=(MU/'Build/odinPkg/RELEASE_CLANGPDB/FV/FVMAIN_COMPACT.inf').read_text().split('[files]')[0]
inf=OUT/'FVMAIN_COMPACT.inf';inf.write_text(template+'[files]\n'+''.join('EFI_FILE_NAME = '+str(p)+'\n' for p in (secffs,compact)))
run([BT/'GenFv.exe','-i',inf,'-r','0x9fd00000','-o',OUT/'UniXNU-odin.fd'])
assert (OUT/'UniXNU-odin.fd').stat().st_size==0x200000
record={'firmware_sha256':sha(OUT/'UniXNU-odin.fd'),'fd_base':'0x9fd00000','fd_bytes':0x200000,
 'baseline_fd_sha256':sha(BASEOUT/'baseline.fd'),'retained_exact_files':retained,'excluded_legacy_apps':excluded,
 'mmcx_hold_provider_sha256':sha(rpmhpe),'darwinboot_guid':darwin,'new_sec_fdt_hob':True,
 'device_tested':False,'kernel_or_system_embedded_in_firmware':False,'remote_media':desktop,'remote_media_bds':options.remote_media_bds}
(OUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
print('Firmware assembled',len(retained),'exact baseline files retained',record['firmware_sha256'])
