"""Qualify observed EL0 traps against unique original-cache instruction runs.

Read-only guest analysis. It does not change an exception, process or image.
Each replay has its own cache ASLR; never borrow a slide from another replay.
"""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,re,struct,sys

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
from symbolicate_ios_stacks import Cache,DEFAULT
import native_prelink as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',required=True)
p.add_argument('--build-tag',required=True)
a=p.parse_args();assert a.tag.isalnum() and a.build_tag.isalnum()
run=DEV/('build/qemu-early-entry-'+a.tag)
build=DEV/('build/display-owner-'+a.build_tag)
trace=(run/'trace.log').read_text()
verification=json.loads((run/'verification.json').read_text())
digest=lambda data:hashlib.sha256(data).hexdigest()
assert verification['kernel_sha256']==digest((build/'kernel.prelinked.experimental.macho').read_bytes())
pcs=Counter(int(x,16) for x in re.findall(
    r'Taking exception 7 \[Breakpoint\][^\n]*\n\.\.\.from EL0 to EL1\n(?:[^\n]*\n){2}\.\.\.with ELR (0x[0-9a-f]+)',trace))
instructions={int(addr,16):int(word,16) for addr,word in re.findall(
    r'^(0x[0-9a-f]+):  ([0-9a-f]{8})  ',trace,re.M)}
c=Cache(DEFAULT);traps=[]
for pc,count in pcs.items():
    if pc not in instructions or instructions[pc]&0xffe0001f!=0xd4200000:
        traps.append(dict(runtime_pc=hex(pc),count=count,unique_original_match=False,
            unresolved_reason='Trap observed but no unambiguous BRK instruction in the bounded translation trace'))
        continue
    start=pc
    while pc-start<44 and start-4 in instructions:start-=4
    if pc-start<8:
        traps.append(dict(runtime_pc=hex(pc),count=count,unique_original_match=False,
            unresolved_reason='Insufficient adjacent instructions for independent image matching'))
        continue
    needle=b''.join(struct.pack('<I',instructions[v]) for v in range(start,pc+4,4))
    hits=[]
    for lo,hi,fo,data in c.maps:
        at=data.find(needle,fo,fo+hi-lo)
        while at>=0:
            hits.append(lo+at-fo);at=data.find(needle,at+1,fo+hi-lo)
    if len(hits)!=1:
        # Standalone processes have their own ASLR and are not in this cache.
        # Preserve their actual trap for a separate executable match; never
        # borrow another process's slide or discard the rest of this run.
        traps.append(dict(runtime_pc=hex(pc),count=count,matched_instructions=needle.hex(),
            instruction_start=hex(start),unique_original_match=False,
            unresolved_reason='No unique shared-cache match; inspect exact standalone executable',
            shared_cache_matches=len(hits)))
        continue
    slide=start-hits[0];assert slide>=0 and slide%4096==0
    original_pc=pc-slide
    row=dict(runtime_pc=hex(pc),original_pc=hex(original_pc),count=count,
        cache_slide=hex(slide),original_image=c.resolve(original_pc),
        matched_bytes=len(needle),unique_original_match=True,matched_instructions=needle.hex())
    if original_pc==0x1ae3a58c0:
        assert c.read(0x1ae3acd04,14)==b'AppleKeyStore\0'
        assert c.read(0x1ae3acce4,18)==b'MKBEventsRegister\0'
        row['qualification']='MKBEventsRegister: missing AppleKeyStore matching service'
    traps.append(row)
c.close()
logs=json.loads((run/'printf.json').read_text())
selected=[r for r in logs if any(s in (r['format'] or '') for s in
    ('odin display:','OdinLegacyGOPDisplay:','odin keyevents:','odin aks:'))]
aks_methods=Counter()
macf=Counter()
signature_rejections=Counter()
for row in logs:
    fmt=row.get('format') or ''
    if fmt.startswith('odin aks: selector '):
        s=row['slots']
        aks_methods[(s[0],s[1],s[2],s[3],s[4]&0xffffffff)]+=1
    if 'failed MACF' in fmt:
        macf[row.get('strings',{}).get('0','unknown')]+=1
    if 'rejecting signature' in fmt:
        signature_rejections[row.get('strings',{}).get('0','unknown')]+=1
aks_counts={}
counts_file=run/'symbol-_odin_aks_calls.bin'
if counts_file.exists():
    data=counts_file.read_bytes()
    aks_counts={str(i):n[0] for i,n in enumerate(struct.iter_unpack('<I',data)) if n[0]}
opened_file=run/'symbol-_odin_aks_opened.bin'
aks_state=dict(opened=int.from_bytes(opened_file.read_bytes()[:4],'little') if opened_file.exists() else None,
    captured_selector_counts=aks_counts,
    counter_capture_bytes=counts_file.stat().st_size if counts_file.exists() else 0,
    bounded_method_logs=[dict(selector=k[0],input_scalars=k[1],output_scalars=k[2],
        output_structure_bytes=k[3],result=hex(k[4]),logged_calls=n) for k,n in sorted(aks_methods.items())],
    macf_failures=dict(macf))
surface_file=run/'symbol-_odin_surface_inspections.bin'
surface_state=None
if surface_file.exists():
    counters=struct.unpack('<16I',surface_file.read_bytes())
    surface_state=dict(requests=counters[0],surfaces=counters[1],wrong_class=counters[2],backed_surfaces=counters[3])
    # Counters 4..12 are emitted by the opt-in CPU presenter. A copied frame
    # and original-family retirement establish that path, not desktop readiness.
    surface_state['cpu_presentation']=dict(zip(
        ('accepted','rejected','kicks','copied','retired','map_failures',
         'activation_refused','outside_workloop_gate','ready_request_mismatch'),
        counters[4:13]))
values={f.name[7:-4]:int.from_bytes(f.read_bytes()[:4],'little')
    for f in run.glob('symbol-*.bin') if f.name.endswith(('_stage.bin','_status.bin'))}
live_file=run/'userspace-live.log'
services=None
if live_file.exists():
    lines=live_file.read_text(encoding='utf8',errors='replace').splitlines()
    labels=('com.apple.SpringBoard','com.apple.backboardd',
            'com.apple.chronod','com.apple.liveactivitiesd')
    lifecycle={label:[] for label in labels}
    failures=Counter();denials=Counter()
    for line in lines:
        for label in labels:
            if re.search(r'/'+re.escape(label)+r'(?: \[|\))',line) and any(
                    term in line for term in ('service state:','Successfully spawned',
                                             'exited','EXITED','crashed')):
                lifecycle[label].append(line)
        failed=re.search(r'failed lookup: name = ([^,]+),.*requestor = ([^,]+),',line)
        if failed:failures[failed.groups()]+=1
        denied=re.search(r'denied lookup: name = ([^,]+),.*requestor = ([^,]+),',line)
        if denied:denials[denied.groups()]+=1
    services=dict(source=live_file.name,captured_lines=len(lines),
        last_captured_line=lines[-1] if lines else None,
        lifecycle={label:rows[-32:] for label,rows in lifecycle.items()},
        missing_service_lookups=[dict(service=k[0],requestor=k[1],logged_count=n)
            for k,n in failures.most_common(64)],
        denied_service_lookups=[dict(service=k[0],requestor=k[1],logged_count=n)
            for k,n in denials.most_common(64)],
        lifecycle_is_not_ui_readiness=True)
panic=None
if (run/'panic.json').exists():
    panic=json.loads((run/'panic.json').read_text())
    blob=(build/'native-real-iig.macho').read_bytes();symbols=np.exports(blob,np.macho(blob))
    # Original panic formatter's xnu saved-state PC is its second vararg.
    if panic['format'].startswith('%s at pc '):
        pc=panic['slots'][1];near=max(v for v in symbols if v<=pc)
        panic['resolved_pc']=dict(address=hex(pc),symbols=symbols[near],offset=hex(pc-near))
client_observations=None
observer_file=run/'register-observations.json'
if observer_file.exists():
    contract=json.loads((build/'display-observer-contract.json').read_text())
    assert contract['passed'] and contract['candidate_sha256']==verification['kernel_sha256']
    observed=json.loads(observer_file.read_text());pending={};calls=[];unmatched=[]
    for row in observed['records']:
        regs={k:int(v,16) for k,v in row['registers'].items()}
        if row['address']==contract['entry']:
            frame=regs['SP']+contract['return_sp_offset_from_entry']
            entry=dict(client=hex(regs['X00']),selector=regs['X01']&0xffffffff,
                       ordinal=row['ordinal'],frame=hex(frame),caller=hex(regs['X30']))
            if 'payload' in row:entry['payload']=row['payload']
            pending.setdefault(frame,[]).append(entry)
        elif row['address']==contract['returned']:
            frame=regs['SP']
            if pending.get(frame):
                entry=pending[frame].pop()
                entry['result']=hex(regs['X00']&0xffffffff);calls.append(entry)
            else:unmatched.append(row)
    summarized=Counter((row['selector'],row['result']) for row in calls)
    client_observations=dict(source=observer_file.name,counts=observed['counts'],
        disabled_at_limit=observed['disabled_at_limit'],
        completed_calls=[dict(selector=k[0],result=k[1],count=n) for k,n in sorted(summarized.items())],
        pending_entries=[row for stack in pending.values() for row in stack],
        unmatched_returns=len(unmatched),calls=calls,
        method_bytes_modified=False)
from PIL import Image
fb=(run/'framebuffer.bin').read_bytes();assert len(fb)==1080*2400*4
Image.frombytes('RGB',(1080,2400),fb,'raw','BGRX').save(run/'framebuffer.png')
result=dict(scope='Computer-only original iOS16 runtime; no device commands',
    kernel_sha256=verification['kernel_sha256'],trace_sha256=digest((run/'trace.log').read_bytes()),
    boot_args=verification['boot_args'],observed_el0_breakpoints=traps,
    stage_values=values,provider_logs=selected,keystore=aks_state,surface_inspection=surface_state,
    launch_services=services,display_client_observations=client_observations,
    signature_rejections=dict(signature_rejections),panic=panic,
    framebuffer_png='framebuffer.png',desktop_verified=False,
    presentation_implemented=bool(surface_state and
        surface_state['cpu_presentation']['copied'] and
        surface_state['cpu_presentation']['retired']),
    desktop_requires_visual_verification=True,device_commands_executed=False)
(run/'desktop-runtime-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='provider_logs'},indent=2))
