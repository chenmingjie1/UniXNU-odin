"""Archive computer-only display work with failures and actual runtime limits."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,tarfile
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
OUT=ROOT/'outputs/MIX4-UniXNU-display-u25'
OUT.mkdir(exist_ok=True)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
latest=DEV/'build/display-owner-u25'
assert json.loads((latest/'display-link-audit.json').read_text())['passed']
assert json.loads((latest/'independent-audit.json').read_text())['passed']
runs=[]
for tag,build in [('u18scale','u18'),('u19mappedready','u19'),('u20chosenscale','u19'),
    ('u21keyevents','u21a'),('u22keyregistered','u22'),('u23keystateram','u23'),
    ('u24aksclassname','u24'),('u24desktopwrites','u24'),('u25surfaceinspect','u25')]:
    folder=DEV/('build/qemu-early-entry-'+tag)
    v=json.loads((folder/'verification.json').read_text())
    row=dict(tag=tag,build=build,kernel_sha256=v['kernel_sha256'],seconds=v['observation_seconds'],
        verification=str((folder/'verification.json').relative_to(ROOT)),desktop_verified=False)
    for name in ('verification.json','desktop-runtime-analysis.json','panic.json','printf.json',
        'framebuffer.png','userspace-live.log','command.json'):
        path=folder/name
        if path.exists():
            target=OUT/'runtime'/tag/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
    if (folder/'desktop-runtime-analysis.json').exists():
        row['analysis']=json.loads((folder/'desktop-runtime-analysis.json').read_text())
    runs.append(row)
archive=OUT/'odin-display-u25-source-and-audits.tar.gz'
paths=[]
paths+=list((DEV/'drivers/OdinDisplay').glob('*'))
paths+=[DEV/'README.md',DEV/'porting.toml']
for name in ('build_odin_display_owner.py','prepare_odin_display_interface.py','check_odin_display_interface.py',
    'audit_odin_display_link.py','audit_ios16_surface.py','discover_ios16_surface_fields.py',
    'analyze_host_desktop_runtime.py','run_u15_host_display.ps1','audit_ios16_aks_state.py',
    'prepare_display_scale_adt.py','audit_odin_display_state.py','archive_display_u25.py'):
    paths.append(DEV/'scripts'/name)
paths+=list((DEV/'build/display-analysis-ios16').glob('u2*.txt'))
paths+=list((DEV/'build/display-analysis-ios16').glob('u2*.json'))
paths+=[DEV/'build/display-analysis-ios16/u20-chosen-scale.adt',
    DEV/'build/display-owner-u19/state-request-qualification.json']
for tag in ('u19','u21a','u22','u23','u24','u25'):
    folder=DEV/('build/display-owner-'+tag)
    if not folder.exists():continue
    paths+=list((folder/'source').glob('*'))
    for suffix in ('*.json','*.log','*.S','*.sh','*.o'):
        paths+=list(folder.glob(suffix))
paths=sorted(set(p for p in paths if p.is_file()))
with tarfile.open(archive,'w:gz') as tar:
    for path in paths:tar.add(path,arcname=path.relative_to(ROOT))
record=dict(updated_at=datetime.now(timezone.utc).isoformat(),scope='computer only; no phone commands',
    candidate=dict(path=str((latest/'kernel.prelinked.experimental.macho').relative_to(ROOT)),
        sha256=digest(latest/'kernel.prelinked.experimental.macho'),phone_boot_image=False),
    desktop_verified=False,presentation_implemented=False,device_commands_executed=False,
    fixed=['chosen display-scale uses original u32 MobileGestalt reader',
        'AppleKeyStore notification lookup and late metaclass registration',
        'AppleKeyStoreUserClient original sandbox class matching; actual selectors 0,7,17,35 succeed'],
    surface_progress='Exact original iOS16 getters linked; slot282 inspection only, still rejects swaps',
    blockers=['Original IOSurface request queue ownership, fences, copy and retirement',
        'Complete SpringBoard rendering and verify visible desktop',
        'MIX4 platform/PMGR and large root memory handoff', 'Native ST HID and A660 Metal'],
    failed_candidates_preserved=['u18 environment-only scale did not set preferredScale',
        'u21a registered a raw class name without postModLoad and panicked',
        'u23 custom client class name failed original MACF checks 587 times'],
    replays=runs,source_archive=dict(file=archive.name,sha256=digest(archive),files=len(paths)))
(OUT/'progress.json').write_text(json.dumps(record,indent=2)+'\n')
status_path=DEV/'migration-status.json'
status=json.loads(status_path.read_text())
status.update(updated_at=record['updated_at'],
    phase='Host-only u25: state service matching corrected; surface request inspection linked; presentation incomplete',
    blockers=record['blockers'],host_selected_kernel=record['candidate']['path'].replace('work/UniXNU-odin/',''),
    host_selected_kernel_sha256=record['candidate']['sha256'],
    host_evidence='outputs/MIX4-UniXNU-display-u25/progress.json',
    host_new_boot_image_created=False,latest_host_candidate_device_tested=False)
status['display_u25']=dict(evidence='outputs/MIX4-UniXNU-display-u25/progress.json',
    candidate_sha256=record['candidate']['sha256'],linked=True,executed=True,
    original_display_start_verified=True,scale_assertion_fixed=True,
    keystore_state_queries_verified=True,surface_accessors_linked=True,
    runtime_surface_inspection=runs[-1].get('analysis',{}).get('surface_inspection'),
    presentation_implemented=False,desktop_verified=False,device_commands_executed=False)
status_path.write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
manifest={str(p.relative_to(OUT)):digest(p) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(output=str(OUT),files=len(manifest),archive_sha256=digest(archive),
    latest_kernel_sha256=record['candidate']['sha256'],desktop_verified=False),indent=2))
