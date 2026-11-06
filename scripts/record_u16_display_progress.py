"""Save measured display integration results without promoting them to hardware."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import argparse,hashlib,json,struct,sys,tarfile
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--latest',choices=('u16','u17'),default='u17')
a=p.parse_args()
OUT=ROOT/('outputs/MIX4-UniXNU-display-'+a.latest);OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def measured(tag,build):
    run=DEV/('build/qemu-early-entry-'+tag)
    verification=json.loads((run/'verification.json').read_text())
    assert verification['kernel_sha256']==digest(build/'kernel.prelinked.experimental.macho')
    logs=json.loads((run/'printf.json').read_text())
    start=[r for r in logs if r['format']=='odin display: original start returned %d\n']
    mapped=[r for r in logs if r['format']=='OdinLegacyGOPDisplay: mapped %ux%u, %llu bytes; presentation not implemented\n']
    assert len(start)==len(mapped)==1 and start[0]['slots'][0]==1
    assert mapped[0]['slots'][:3]==[1080,2400,10368000]
    stage=struct.unpack('<I',(run/'symbol-_odin_display_owner_stage.bin').read_bytes()[:4])[0]
    status=struct.unpack('<i',(run/'symbol-_odin_display_owner_status.bin').read_bytes()[:4])[0]
    assert stage==8 and status==0
    panic=json.loads((run/'panic.json').read_text()) if (run/'panic.json').exists() else None
    result=dict(path=run.relative_to(ROOT).as_posix(),kernel_sha256=verification['kernel_sha256'],
        original_start_success=True,framebuffer=[1080,2400,4320],framebuffer_mapped_bytes=10368000,
        owner_stage=stage,owner_status=status,panic=panic,
        data_reads=int.from_bytes((run/'symbol-_native_ram_block_reads.bin').read_bytes()[:8],'little'),
        data_writes=int.from_bytes((run/'symbol-_native_ram_block_writes.bin').read_bytes()[:8],'little'),
        io_failures=int.from_bytes((run/'symbol-_native_ram_block_failures.bin').read_bytes()[:8],'little'))
    if (run/'display-runtime-analysis.json').exists():
        result['display_runtime_analysis']=json.loads((run/'display-runtime-analysis.json').read_text())
    return result

u15=measured('u15desktop',DEV/'build/display-owner-u15')
u16=measured('u16dotpitchfixed',DEV/'build/display-owner-u16')
u17=measured('u17query74',DEV/'build/display-owner-u17') if a.latest=='u17' else None
files=[]
for tag in (('u15','u16','u17') if u17 else ('u15','u16')):
    build=DEV/('build/display-owner-'+tag)
    for p in build.iterdir():
        if p.is_file() and p.suffix in ('.py','.S','.o','.a','.log','.txt','.json') and p.name!='prelink-emission-report.json':files.append(p)
    files+=list((build/'source').glob('*'))
for tag in (('u15display','u15desktop','u16dotpitchfixed','u17query74') if u17 else ('u15display','u15desktop','u16dotpitchfixed')):
    run=DEV/('build/qemu-early-entry-'+tag)
    for p in run.iterdir():
        if p.name in ('verification.json','panic.json','printf.json','registers.json','userspace-live.log','command.json',
                      'display-runtime-analysis.json','framebuffer.png') or p.name.startswith('symbol-'):
            files.append(p)
for name in ('build_odin_display_owner.py','install_odin_display_owner.py','audit_odin_display_link.py',
             'audit_odin_dot_pitch.py','disassemble_ios_cache_display.py','check_odin_display_interface.py',
             'audit_odin_query74.py','run_u15_host_display.ps1','record_u16_display_progress.py',
             'prepare_odin_display_interface.py'):
    files.append(DEV/'scripts'/name)
if u17:files.append(DEV/'scripts/analyze_u17_display_runtime.py')
files+=list((DEV/'build/display-analysis-ios16').glob('u15-*.txt'))
files+=list((DEV/'build/display-analysis-ios16').glob('u16-*.txt'))
files += [DEV/'README.md',DEV/'porting.toml',DEV/'drivers/OdinDisplay/README.md']
record=dict(updated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    scope='Computer-only original display registration and client integration; no physical qualification',
    target_os='iOS 16.5 / 20F66',linked=True,executed=True,
    original_display_start_runtime_verified=True,original_userclient_entered=True,
    u15=u15,u16=u16,u17=u17,source_dispatch_entries_checked=338,final_linked_dispatch_entries_checked=338,
    original_executable_kext_ranges_preserved=30,original_relocated_pointers_checked=65319,
    dot_pitch_contract='Actual selector28 -> provider slot188, uint32 output, original property-missing 0xe00002f0',
    desktop_verified=False,frames_presented=False,physical_display_verified=False,
    native_touch_verified=False,a660_metal_verified=False,device_commands_executed=False,
    new_phone_boot_image_created=False,
    stopped_stale_replay=dict(path='work/UniXNU-odin/build/qemu-early-entry-u16dotpitch',
        reason='XNU make did not track new link archives; stale u15 kernel found by final-symbol audit. Explicitly stopped; no qualification claimed.'),
    files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in sorted(set(files))])
for name in ('dot-pitch-qualification.json','display-link-audit.json','independent-audit.json'):
    (OUT/name).write_bytes((DEV/'build/display-owner-u16'/name).read_bytes())
archive=OUT/'odin-display-u16-source-link-runtime.tar.gz'
if u17:
    (OUT/'query74-qualification.json').write_bytes((DEV/'build/display-owner-u17/query74-qualification.json').read_bytes())
    (OUT/'u17-display-link-audit.json').write_bytes((DEV/'build/display-owner-u17/display-link-audit.json').read_bytes())
    archive=OUT/'odin-display-u17-source-link-runtime.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for p in sorted(set(files)):t.add(p,arcname=p.relative_to(ROOT).as_posix())
record['archive']=dict(path=archive.relative_to(ROOT).as_posix(),sha256=digest(archive))
(OUT/'progress.json').write_text(json.dumps(record,indent=2)+'\n')
status_path=DEV/'migration-status.json';status=json.loads(status_path.read_text())
status['updated_at']=record['updated_at']
status['phase']='Host-only: original display starts; FBSDisplayMode configuration assertion and surface presentation block desktop'
status['display_'+a.latest]=dict(evidence=OUT.relative_to(ROOT).as_posix()+'/progress.json',
    candidate_sha256=(u17 or u16)['kernel_sha256'],linked=True,executed=True,
    original_display_start_verified=True,desktop_verified=False,device_commands_executed=False)
status_path.write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('files','u15','u16','u17')},indent=2))
