"""Replay the native kernel's early entry on a generic ARM CPU, without a phone.

The memory layout follows the photographed u05 handoff. This can replay CPU
entry, the source kernel and original userspace fixtures; it does not emulate
SM8350 peripherals or qualify a phone desktop.
"""
from pathlib import Path
import argparse,hashlib,json,re,socket,struct,subprocess,time,shutil
from adt_codec import decode,encode,lookup
ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--trampoline',action='store_true')
parser.add_argument('--resident-secondary',action='store_true',help='QEMU-only SMP core7/HVC launch with production secondary entry; CPU affinity overlay never deployed')
parser.add_argument('--cpu', choices=['cortex-a55','cortex-a76','cortex-a78ae'], default='cortex-a76', help='Actual generic ARM CPU model to replay; does not emulate SM8350 peripherals')
parser.add_argument('--handoff-only',action='store_true')
parser.add_argument('--kernel',type=Path,default=DEV/'build/ios16-prelink/kernel.prelinked.experimental.macho')
parser.add_argument('--adt',type=Path,default=DEV/'build/prelinked-payload/esp/EFI/UniXNU/Payloads/kernel.macho.adt')
parser.add_argument('--virt-platform',action='store_true',help='QEMU-only GICv3 and timer ADT overlay, never deployed')
parser.add_argument('--qemu-vmm-present',action='store_true',help='Report actual QEMU identity in replay /defaults only; never deploy this overlay')
parser.add_argument('--ramdisk',type=Path,help='Raw reserved RAMDisk fixture that fits --owned-memory-size (QEMU only)')
parser.add_argument('--data-ramdisk',type=Path,help='Separate writable RAM Data seed; never a host disk or phone partition')
parser.add_argument('--skip-data-checkpoint',action='store_true',help='Early bootstrap replay only: do not export a modified Data fixture')
parser.add_argument('--data-no-sep',action='store_true',help='QEMU-only /filesystems/DoNotUseSEP declaration for unencrypted RAM Data')
parser.add_argument('--trust-cache',type=Path,help='Explicit development trust-cache offset bundle reserved in QEMU RAM')
parser.add_argument('--owned-memory-size',type=lambda value:int(value,0),default=0x20000000,help='QEMU-owned RAM window only, aligned, at most 4GiB; not a phone allocation claim')
parser.add_argument('--boot-args',default='-v serial=0 cpus=1')
parser.add_argument('--output-tag',default='')
parser.add_argument('--halt-at', help='QEMU-only b . at an exact native symbol; does not edit kernel file')
parser.add_argument('--fault-at', help='QEMU-only BRK #0x123 at an exact native symbol')
parser.add_argument('--fault-handler', default='_odin_early_exception', help='Exact expected native handler for the deliberate QEMU fault')
parser.add_argument('--break-at', help='QEMU GDB hardware breakpoint; leaves integrity-protected code unchanged')
parser.add_argument('--break-address',type=lambda value:int(value,0),help='Exact original-kext VA for a non-mutating hardware breakpoint')
parser.add_argument('--read-symbol',action='append',default=[],help='Snapshot 64 bytes at an exact native symbol')
parser.add_argument('--read-register-memory',action='append',default=[],help='Snapshot VA in a stopped register: X21:4096 or SP:0x170')
parser.add_argument('--read-physical-memory',action='append',default=[],help='QEMU-only physical snapshot: 0xf1084000:4096')
parser.add_argument('--require-breakpoint',action='store_true',help='Fail if the requested hardware breakpoint is not reached within the replay window')
parser.add_argument('--user-trap-snapshot',action='store_true',help='At handle_breakpoint only, preserve actual EL0 saved state and display/exception objects; computer replay only')
parser.add_argument('--ui-thread-plan',type=Path,help='Exact compiler layout for pinned upstream read-only UI thread and fatal-message capture')
parser.add_argument('--ui-thread-interval',type=int,default=0,help='Periodic read-only UI snapshots through the existing controller; 30..600 seconds')
parser.add_argument('--data-log-path',action='append',default=[],help='Bounded host RAM Data log inspection during periodic UI snapshots')
parser.add_argument('--seconds',type=float,default=5,help='Bounded host replay observation window, 1 to 1800 seconds; launch asynchronously for long runs')
parser.add_argument('--allow-host-stop',action='store_true',help='End observation and preserve evidence when this run receives stop-request.txt; host only')
parser.add_argument('--frame-interval',type=int,default=0,help='Optional read-only live scanout snapshots, seconds; frames captured while running may tear')
parser.add_argument('--printf-log',action='store_true',help='Capture native printf calls with non-mutating GDB hardware breakpoints')
parser.add_argument('--log-function',action='append',default=[],help='Additional variadic log function to capture with --printf-log')
parser.add_argument('--log-address',type=lambda value:int(value,0),action='append',default=[],help='Exact audited original-kext variadic logger VA, with --printf-log')
parser.add_argument('--observe-address',type=lambda value:int(value,0),action='append',default=[],help='Read-only register observations at exact backed code addresses; requires --printf-log')
parser.add_argument('--max-observations',type=int,default=256,help='Per-address observation bound; breakpoint is removed on reaching this limit')
parser.add_argument('--display-client-payload',action='store_true',help='Snapshot first four iOS16 display argument payloads per selector; computer replay only')
parser.add_argument('--syscall-log',action='store_true',help='With --printf-log, record real ARM64 BSD syscall arguments via hardware breakpoints')
parser.add_argument('--write-log',action='store_true',help='With --printf-log, trace write/write_nocancel only; avoids stopping on every other syscall')
parser.add_argument('--max-syscalls',type=int,default=10000,help='Bounded trace record limit; at most 50000 for service bootstrap')
options=parser.parse_args()
assert 1 <= options.seconds <= 1800
assert options.frame_interval == 0 or 30 <= options.frame_interval <= 600
assert 1000 <= options.max_syscalls <= 50000
assert not options.qemu_vmm_present or options.virt_platform
assert not options.handoff_only or options.trampoline
assert not options.resident_secondary or (not options.trampoline and not options.printf_log and options.output_tag)
assert not options.syscall_log or options.printf_log
assert not options.write_log or (options.printf_log and not options.syscall_log)
assert not options.observe_address or options.printf_log
assert 1 <= options.max_observations <= 4096
assert len(options.observe_address)==len(set(options.observe_address))<=16
assert not options.display_client_payload or 0xfffffff004c012a0 in options.observe_address
assert not options.data_ramdisk or options.ramdisk
assert not options.skip_data_checkpoint or (options.data_ramdisk and options.break_at and not options.printf_log)
assert not options.data_no_sep or options.data_ramdisk
assert not options.user_trap_snapshot or options.break_at=='_handle_breakpoint'
assert not options.ui_thread_plan or (options.printf_log and options.break_at!='_handle_breakpoint')
assert options.ui_thread_interval==0 or (options.ui_thread_plan and 30<=options.ui_thread_interval<=600)
assert not options.data_log_path or (options.ui_thread_interval and options.data_ramdisk)
assert all(path in ('/tmp/odin-host-input.log', '/tmp/odin-sb-unlock.log') for path in options.data_log_path)
assert sum(bool(x) for x in (options.halt_at,options.fault_at,options.break_at,options.break_address))<=1
OUT=DEV/('build/qemu-u06-handoff-markers' if options.handoff_only else 'build/qemu-early-entry-u06' if options.trampoline else 'build/qemu-early-entry');OUT.mkdir(exist_ok=True)
if options.output_tag:
    assert options.output_tag.isalnum()
    OUT=DEV/('build/qemu-early-entry-'+options.output_tag);OUT.mkdir(exist_ok=True)
kernel=options.kernel
b=kernel.read_bytes();segments=[];pos=32;entry=None;symtab=None
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,n=struct.unpack_from('<II',b,pos)
    if cmd==25:
        name,va,vs,fo,fs=struct.unpack_from('<16s4Q',b,pos+8)
        if vs:segments.append((name,va,vs,fo,fs))
    if cmd==5:entry=struct.unpack_from('<Q',b,pos+272)[0]
    if cmd==2:symtab=struct.unpack_from('<4I',b,pos+8)
    pos+=n
symbols={}
for i in range(symtab[1]):
    name,t,s,d,value=struct.unpack_from('<IBBHQ',b,symtab[0]+i*16)
    start=symtab[2]+name;end=b.index(b'\0',start)
    symbol=b[start:end].decode('utf-8','replace')
    if t & 0x0e == 0x0e:
        symbols[symbol]=value
base=min(s[1] for s in segments);end=max(s[1]+s[2] for s in segments)
if options.break_address:
    assert options.break_address%4==0 and any(va<=options.break_address<va+fs for _,va,_,_,fs in segments)
    options.break_at='_replay_absolute_breakpoint'
    symbols[options.break_at]=options.break_address
physical=0xecbd0000;window=options.owned_memory_size
assert 0x10000000<=window<=0x100000000 and window%0x200000==0
align=lambda n,a:(n+a-1)&~(a-1)
args=align(physical+end-base,0x4000);tree= args+0x1000
adt=options.adt.read_bytes()
source_adt_sha256=hashlib.sha256(adt).hexdigest()
adt_tree=decode(adt)
if options.resident_secondary:
    lookup(adt_tree,'cpus','cpu0')['reg']=struct.pack('<I',7)
    adt=encode(adt_tree)
if options.virt_platform:
    # pe_identify_machine treats a zero SoC base as absent. Keep the real
    # QEMU GIC region as the nonzero parent window, with relative child regs.
    lookup(adt_tree,'arm-io')['ranges']=struct.pack('<3Q',0,0x08000000,0x10000000)
    lookup(adt_tree,'arm-io','intc')['reg']=struct.pack('<4Q',0,0x10000,0xa0000,0x20000)
    adt=encode(adt_tree)
if options.qemu_vmm_present:
    lookup(adt_tree,'defaults')['vmm-present']=struct.pack('<I',1)
    adt=encode(adt_tree)
ramdisk_bytes=0;ramdisk_pa=None;trust_data=b'';trust_pa=None
data_bytes=0;data_pa=None
if options.data_ramdisk:
    data_bytes=options.data_ramdisk.stat().st_size
    assert 0<data_bytes<=0x20000000 and data_bytes%4096==0
    mappings=lookup(adt_tree,'chosen','memory-map')
    assert mappings.get('OdinDataRAMDisk', bytes(16)) == bytes(16)
    mappings['OdinDataRAMDisk']=bytes(16)
    if options.data_no_sep:
        try:
            filesystems=lookup(adt_tree,'filesystems')
        except StopIteration:
            filesystems={'name':b'filesystems\0'}
            adt_tree[1].append((filesystems,[]))
        assert filesystems.get('DoNotUseSEP', struct.pack('<I',1)) == struct.pack('<I',1)
        filesystems['DoNotUseSEP']=struct.pack('<I',1)
    adt=encode(adt_tree)
if options.trust_cache:
    assert options.ramdisk, 'Trust cache replay requires an explicit root image'
    trust_data=options.trust_cache.read_bytes()
    assert 0<len(trust_data)<=16*1024*1024
    mappings=lookup(adt_tree,'chosen','memory-map')
    assert mappings.get('TrustCache', bytes(16)) == bytes(16)
    mappings['TrustCache']=bytes(16)
    adt=encode(adt_tree)
    trust_pa=align(tree+len(adt),4096)
    mappings['TrustCache']=struct.pack('<2Q',trust_pa,len(trust_data))
    adt=encode(adt_tree)
if options.ramdisk:
    ramdisk_bytes=options.ramdisk.stat().st_size
    assert 0<ramdisk_bytes<window and ramdisk_bytes%4096==0
    mappings=lookup(adt_tree,'chosen','memory-map')
    assert mappings['RAMDisk']==bytes(16),'Replay requires an unbound RAMDisk slot'
    # The prefix loader is padded to 16K; keep its ROM region disjoint.
    ramdisk_pa=align(trust_pa+len(trust_data) if trust_data else tree+len(adt),0x4000)
    mappings['RAMDisk']=struct.pack('<2Q',ramdisk_pa,ramdisk_bytes)
    adt=encode(adt_tree)
if data_bytes:
    data_pa=align(ramdisk_pa+ramdisk_bytes,0x4000)
    mappings['OdinDataRAMDisk']=struct.pack('<2Q',data_pa,data_bytes)
    adt=encode(adt_tree)
used=align((data_pa+data_bytes if data_bytes else ramdisk_pa+ramdisk_bytes if ramdisk_bytes else tree+len(adt))-physical,0x4000)
assert used < window
(OUT/'replay.adt').write_bytes(adt)
# QEMU loads the disk separately at its reserved PA, so the host does not
# duplicate a multi-gigabyte disk into Python's kernel-prefix buffer.
memory=bytearray(align((trust_pa+len(trust_data) if trust_data else tree+len(adt))-physical,0x4000))
for _,va,vs,fo,fs in segments:memory[va-base:va-base+fs]=b[fo:fo+fs]
for name, instruction in [(options.halt_at, 0x14000000), (options.fault_at, 0xd4202460)]:
    if name:
        assert name in symbols, 'No exact symbol for QEMU injection: '+name
        address=symbols[name]
        assert any(va<=address<va+fs for _,va,_,_,fs in segments)
        struct.pack_into('<I',memory,address-base,instruction)
off=args-physical
struct.pack_into('<HHI4Q',memory,off,2,2,0,base,physical,window,physical+used)
struct.pack_into('<6Q',memory,off+0x28,0xea600000,0 if options.trampoline or options.resident_secondary else 1,4320,1080,2400,32)
struct.pack_into('<Q',memory,off+0x60,base+tree-physical)
struct.pack_into('<I',memory,off+0x68,len(adt))
command_line=options.boot_args.encode('ascii')+b'\0'
assert len(command_line)<=608
memory[off+0x6c:off+0x6c+len(command_line)]=command_line
struct.pack_into('<Q',memory,off+0x2d8,window)
memory[tree-physical:tree-physical+len(adt)]=adt
if trust_data:
    memory[trust_pa-physical:trust_pa-physical+len(trust_data)]=trust_data
(OUT/'window.bin').write_bytes(memory)
# Position-independent entry stub: x0=args PA, x1=entry PA; interrupts masked.
stub=struct.pack('<4I2Q',0xd5034fdf,0x58000060,0x58000081,0xd61f0020,args,physical+entry-base)
# LDR x0 at +4 -> literal +16; LDR x1 at +8 -> literal +24.
assert len(stub)==32
(OUT/'entry.bin').write_bytes(stub)
if options.trampoline:
    llvm=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
    def compile_raw(source,stem):
        obj=OUT/(stem+'.o');raw=OUT/(stem+'.bin')
        subprocess.run([str(llvm/'clang.exe'),'--target=aarch64-none-elf','-I',str(DEV/'build/darwinboot'),'-c',str(source),'-o',str(obj)],check=True,capture_output=True)
        subprocess.run([str(llvm/'llvm-objcopy.exe'),'-O','binary','--only-section=.text',str(obj),str(raw)],check=True,capture_output=True)
        return raw
    trampoline=compile_raw(Path(__file__).with_name('OdinDarwinEnter.S'),'trampoline')
    values=[args,0x410000f0 if options.handoff_only else physical+entry-base,physical,window,0xea600000,4320*2400,4320,0x41000108]
    assembly='.text\n.globl entry\nentry:\n'+''.join(f'  ldr x{i}, {i+1}f\n' for i in range(8))+'  br x7\n  .balign 8\n'+''.join(f'{i+1}: .quad {v:#x}\n' for i,v in enumerate(values))
    (OUT/'entry.S').write_text(assembly)
    compile_raw(OUT/'entry.S','entry')
if options.resident_secondary:
    from stage_resident_replay import stage
    resident_commands=stage(OUT,DEV,args,physical+entry-base)
    (OUT/'resident-commands.json').write_text(json.dumps(resident_commands,indent=2)+'\n')
ports=[]
for _ in range(2 if options.break_at or options.printf_log else 1):
    with socket.socket() as s:s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1])
cmd=[ROOT/'work/odin-portable-linux/qemu/qemu-system-aarch64.exe',
 '-machine','virt,virtualization=off'+(',gic-version=3' if options.virt_platform else ''),'-cpu',options.cpu+(',cntfrq=19200000' if options.virt_platform else ''),'-accel','tcg',
 '-m','8192' if physical+window>0x140000000 else '4096','-smp','8' if options.resident_secondary else '1','-display','none','-serial','none','-net','none',
 '-device',f'loader,file={OUT / "window.bin"},addr={physical:#x},force-raw=on',
 '-device',f'loader,file={OUT / "entry.bin"},addr=0x41000000,cpu-num=0,force-raw=on',
 '-d','in_asm,int,guest_errors','-D',str(OUT/'trace.log'),
 '-qmp',f'tcp:127.0.0.1:{ports[0]},server=on,wait=off','-no-reboot','-S']
if ramdisk_bytes:
    cmd += ['-device',f'loader,file={options.ramdisk.resolve()},addr={ramdisk_pa:#x},force-raw=on']
if data_bytes:
    cmd += ['-device',f'loader,file={options.data_ramdisk.resolve()},addr={data_pa:#x},force-raw=on']
if options.seconds>=300 and ramdisk_bytes:
    assert shutil.disk_usage(OUT).free >= 18*1024**3, 'Need 18 GiB free for Windows memory backing, trace and a complete Data checkpoint'
(OUT/'command.json').write_text(json.dumps(list(map(str,cmd)),indent=2)+'\n')
if options.break_at or options.printf_log:
    assert not options.break_at or options.break_at in symbols
    cmd += ['-gdb',f'tcp:127.0.0.1:{ports[1]}']
if options.trampoline:
    cmd[cmd.index('-d'):cmd.index('-d')]=['-device',f'loader,file={OUT / "trampoline.bin"},addr=0x41000100,force-raw=on']
    (OUT/'command.json').write_text(json.dumps(list(map(str,cmd)),indent=2)+'\n')
if options.handoff_only:
    (OUT/'stop.bin').write_bytes(struct.pack('<I',0x14000000))
    cmd[cmd.index('-d'):cmd.index('-d')]=['-device',f'loader,file={OUT / "stop.bin"},addr=0x410000f0,force-raw=on']
    (OUT/'command.json').write_text(json.dumps(list(map(str,cmd)),indent=2)+'\n')
reply={}
with (OUT/'qemu.log').open('wb') as log:
    p=subprocess.Popen(list(map(str,cmd)),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+15
        while True:
            if p.poll() is not None:raise RuntimeError((OUT/'qemu.log').read_text(errors='replace'))
            try:s=socket.create_connection(('127.0.0.1',ports[0]),timeout=1);break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        with s:
            # Large RAMDisk loading can still be completing after QMP binds.
            # Bound the startup handshake separately from normal commands.
            s.settimeout(30);f=s.makefile('rwb');f.readline()
            def qmp(name,**kwargs):
                if options.resident_secondary and name=='human-monitor-command':kwargs['cpu-index']=7
                f.write((json.dumps({'execute':name,'arguments':kwargs})+'\n').encode());f.flush()
                while True:
                    o=json.loads(f.readline())
                    if 'return' in o or 'error' in o:return o
            qmp('qmp_capabilities')
            s.settimeout(5)
            if ramdisk_bytes:
                # Check QEMU's actual loader output before XNU can modify RAM.
                # Large-image loading must not be inferred from a command line.
                media_checks=[]
                with options.ramdisk.open('rb') as media:
                    for disk_offset in sorted({0, (ramdisk_bytes//2)&~4095, ramdisk_bytes-4096}):
                        target=OUT/f'loaded-media-{disk_offset:x}.bin'
                        target.unlink(missing_ok=True)
                        qmp('human-monitor-command',**{'command-line':f'pmemsave {ramdisk_pa+disk_offset:#x} 4096 "{target.as_posix()}"'})
                        media.seek(disk_offset)
                        expected=media.read(4096)
                        actual=target.read_bytes() if target.exists() else b''
                        media_checks.append({'offset':disk_offset,'matches_input':actual==expected,
                            'expected_sha256':hashlib.sha256(expected).hexdigest(),
                            'loaded_sha256':hashlib.sha256(actual).hexdigest()})
                (OUT/'loaded-media.json').write_text(json.dumps(media_checks,indent=2)+'\n')
                assert all(check['matches_input'] for check in media_checks), 'QEMU RAMDisk loader did not preserve input bytes'
            # Preserve the stopped CPU evidence even if the later APFS dump fails.
            (OUT/'registers.json').write_text(json.dumps(reply,indent=2)+'\n')
            if data_bytes:
                checks=[]
                with options.data_ramdisk.open('rb') as media:
                    for offset in sorted({0,(data_bytes//2)&~4095,data_bytes-4096}):
                        target=OUT/f'loaded-data-{offset:x}.bin'
                        target.unlink(missing_ok=True)
                        qmp('human-monitor-command',**{'command-line':f'pmemsave {data_pa+offset:#x} 4096 "{target.as_posix()}"'})
                        media.seek(offset)
                        checks.append({'offset':offset,'matches_input':target.read_bytes()==media.read(4096)})
                (OUT/'loaded-data-media.json').write_text(json.dumps(checks,indent=2)+'\n')
                assert all(row['matches_input'] for row in checks)
            def snapshot(address, length, name):
                target=OUT/name
                target.unlink(missing_ok=True)
                response=qmp('human-monitor-command',**{'command-line':f'memsave {address:#x} {length} "{target.as_posix()}"'})
                return target.read_bytes() if target.exists() and target.stat().st_size==length else None
            if options.printf_log:
                # Code bytes and FIPS measurements are unchanged. Temporarily
                # remove the hardware breakpoint and single-step the real first
                # instruction before arming it again, avoiding a repeat trap.
                with socket.create_connection(('127.0.0.1',ports[1]),timeout=5) as gdb:
                    gdb.settimeout(5)
                    def rsp(payload):
                        raw=payload.encode()
                        gdb.sendall(b'$'+raw+b'#'+f'{sum(raw)&255:02x}'.encode())
                        received=b''
                        while b'$' not in received:received+=gdb.recv(1)
                        packet=b''
                        while True:
                            ch=gdb.recv(1)
                            if ch==b'#':break
                            packet+=ch
                        checksum=gdb.recv(2)
                        assert checksum==f'{sum(packet)&255:02x}'.encode()
                        gdb.sendall(b'+')
                        return packet
                    ui_observer=None
                    if options.ui_thread_plan:
                        from ui_thread_observer import Observer
                        plan=json.loads(options.ui_thread_plan.read_text())
                        assert plan['kernel_sha256']==hashlib.sha256(b).hexdigest()
                        assert plan['allproc']==symbols['_allproc']
                        assert plan['thread_snapshot_native_pt_attr']==symbols['_native_pt_attr']
                        gdb.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                        ui_observer=Observer(lambda payload:rsp(payload).decode(),plan)
                        (OUT/'ui-thread-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
                    log_pcs={symbols[name]:name for name in ['_printf',*options.log_function]}
                    if ui_observer:
                        log_pcs[symbols['_handle_breakpoint']]='user_trap_observation'
                    user_trap_count=0
                    if options.syscall_log:
                        log_pcs[symbols['_unix_syscall']]='_unix_syscall'
                    if options.write_log:
                        # write_internal is inlined into both syscall entries
                        # by this exact kernel build. Trace the real entries.
                        for name in ('_write', '_write_nocancel'):
                            log_pcs[symbols[name]]=name
                    for address in options.log_address:
                        assert address%4==0 and any(va<=address<va+fs for _,va,_,_,fs in segments)
                        log_pcs[address]=hex(address)
                    observations=[];observation_counts={address:0 for address in options.observe_address}
                    payload_counts={}
                    if options.display_client_payload:
                        # Independently match the observed iOS16 externalMethod
                        # argument stores before interpreting IOExternalMethodArguments.
                        at=next(fo+0xfffffff004c012a0-va for _,va,_,fo,fs in segments
                                if va<=0xfffffff004c012a0<va+fs)
                        assert b[at:at+12]==bytes.fromhex('ff0302d1fd7b07a9fdc30191')
                        assert b[at+0x18:at+0x24]==bytes.fromhex('a0031ff8a1c31eb8a2031ef8')
                    for address in observation_counts:
                        assert address%4==0 and any(va<=address<va+fs for _,va,_,_,fs in segments)
                        assert address not in log_pcs
                        assert not options.break_at or address!=symbols[options.break_at]
                        log_pcs[address]='register_observation'
                    for address in log_pcs:assert rsp(f'Z1,{address:x},4')==b'OK'
                    if options.break_at:assert rsp(f'Z1,{symbols[options.break_at]:x},4')==b'OK'
                    deadline=time.monotonic()+options.seconds
                    started=time.monotonic();next_frame=started+options.frame_interval;frame_number=0
                    next_ui=started+options.ui_thread_interval;ui_number=0
                    def capture_ui(name):
                        try:
                            captured=ui_observer.capture()
                        except (ValueError,AssertionError) as error:
                            captured=dict(error=str(error),read_only=True)
                        captured['wall_seconds']=time.monotonic()-started
                        (OUT/name).write_text(json.dumps(captured,indent=2)+'\n')
                    def capture_data_logs():
                        from prepare_launch_services_root import apfs
                        target=OUT/'data-live.apfs'
                        result=qmp('human-monitor-command',**{'command-line':f'pmemsave {data_pa:#x} {data_bytes} "{target.as_posix()}"'})
                        record=dict(wall_seconds=time.monotonic()-started,read_only=True,device_commands_executed=False)
                        try:
                            assert not result.get('error') and result.get('return','')=='', result
                            assert target.stat().st_size==data_bytes, 'Incomplete live Data snapshot'
                            container=apfs.Container(target)
                            try:
                                volume=apfs.pick_volume(container,None)
                                record['checkpoint']=container.xid
                                record['logs']={}
                                for path in options.data_log_path:
                                    found=volume.lookup(path)
                                    if found:
                                        inode=volume.inode(found[0])
                                        assert inode.is_reg and inode.size<=65536
                                        record['logs'][path]=inode.contents().decode('utf8','replace')
                                    else:record['logs'][path]=None
                            finally:container.close()
                        except (AssertionError,ValueError,OSError,apfs.ApfsError) as error:
                            record['error']=str(error)
                        with (OUT/'data-log-live.jsonl').open('a',encoding='utf8') as live:
                            live.write(json.dumps(record)+'\n')
                    records=[];syscalls=[]
                    (OUT/'userspace-live.log').unlink(missing_ok=True)
                    (OUT/'display-live.jsonl').unlink(missing_ok=True)
                    qmp('cont')
                    while time.monotonic()<deadline and not (options.allow_host_stop and (OUT/'stop-request.txt').exists()):
                        state=qmp('query-status').get('return',{})
                        if state.get('running'):
                            if options.ui_thread_interval and time.monotonic()>=next_ui:
                                qmp('stop')
                                ui_number+=1
                                capture_ui(f'ui-thread-periodic-{ui_number:03}.json')
                                if options.data_log_path:capture_data_logs()
                                next_ui=time.monotonic()+options.ui_thread_interval
                                qmp('cont')
                            if options.frame_interval and time.monotonic()>=next_frame:
                                frame_number+=1
                                frame=OUT/'periodic-frame-latest.bin'
                                qmp('human-monitor-command',**{'command-line':
                                    f'pmemsave 0xea600000 10368000 "{frame.as_posix()}"'})
                                if frame.exists() and frame.stat().st_size==10368000:
                                    from PIL import Image
                                    pixels=frame.read_bytes()
                                    target=OUT/f'periodic-frame-{frame_number:03}.png'
                                    Image.frombytes('RGB',(1080,2400),pixels,'raw','BGRX').save(target)
                                    with (OUT/'periodic-frames.jsonl').open('a') as live:
                                        live.write(json.dumps(dict(file=target.name,
                                            wall_seconds=time.monotonic()-started,
                                            pixels_sha256=hashlib.sha256(pixels).hexdigest(),
                                            captured_while_running=True,may_be_torn=True))+'\n')
                                next_frame=time.monotonic()+options.frame_interval
                            time.sleep(.01)
                            continue
                        rawregs=qmp('human-monitor-command',**{'command-line':'info registers'}).get('return','')
                        parsed={k:int(v,16) for k,v in re.findall(r'\b(PC|X\d\d|SP)=([0-9a-fA-F]+)',rawregs)}
                        printf_pc=parsed.get('PC')
                        if printf_pc not in log_pcs:break
                        if log_pcs[printf_pc]=='user_trap_observation':
                            user_trap_count+=1
                            trap=ui_observer.fatal(parsed['X00'])
                            trap.update(ordinal=user_trap_count,wall_seconds=time.monotonic()-started)
                            with (OUT/'user-fatal-live.jsonl').open('a',encoding='utf8') as live:
                                live.write(json.dumps(trap)+'\n')
                            assert rsp(f'z1,{printf_pc:x},4')==b'OK'
                            assert rsp('s').startswith((b'T',b'S'))
                            if user_trap_count<64:
                                assert rsp(f'Z1,{printf_pc:x},4')==b'OK'
                            qmp('cont')
                            continue
                        if log_pcs[printf_pc]=='register_observation':
                            observation_counts[printf_pc]+=1
                            observation=dict(address=hex(printf_pc),
                                ordinal=observation_counts[printf_pc],
                                registers={name:hex(parsed[name]) for name in
                                    ('X00','X01','X02','X03','X04','X05','X06','X07','X30','SP')
                                    if name in parsed})
                            if options.display_client_payload and printf_pc==0xfffffff004c012a0:
                                selector=parsed['X01']&0xffffffff
                                payload_counts[selector]=payload_counts.get(selector,0)+1
                                if payload_counts[selector]<=4:
                                    raw=snapshot(parsed['X02'],248,'observed-method-arguments.bin')
                                    if raw:
                                        scalar_ptr=struct.unpack_from('<Q',raw,32)[0]
                                        scalar_count=struct.unpack_from('<I',raw,40)[0]
                                        structure_ptr=struct.unpack_from('<Q',raw,48)[0]
                                        structure_size=struct.unpack_from('<I',raw,56)[0]
                                        payload=dict(argument_hex=raw.hex(),scalar_input_count=scalar_count,
                                                     structure_input_bytes=structure_size)
                                        if scalar_ptr and 0<scalar_count<=16:
                                            values=snapshot(scalar_ptr,scalar_count*8,'observed-method-scalars.bin')
                                            if values:payload['scalar_input']=list(struct.unpack('<'+'Q'*scalar_count,values))
                                        if structure_ptr and 0<structure_size<=4096:
                                            values=snapshot(structure_ptr,structure_size,'observed-method-structure.bin')
                                            if values:payload['structure_input_hex']=values.hex()
                                        observation['payload']=payload
                            observations.append(observation)
                            assert rsp(f'z1,{printf_pc:x},4')==b'OK'
                            assert rsp('s').startswith((b'T',b'S'))
                            if observation_counts[printf_pc]<options.max_observations:
                                assert rsp(f'Z1,{printf_pc:x},4')==b'OK'
                            qmp('cont')
                            continue
                        if log_pcs[printf_pc] in ('_write', '_write_nocancel'):
                            # XNU8796 generated sysproto.h: proc, uap, retval;
                            # uap contains three padded 8-byte argument slots.
                            # Read the actual function arguments; never change
                            # guest data or the syscall result.
                            arguments=snapshot(parsed['X01'],24,'write-arguments.bin')
                            assert arguments is not None
                            fd,buffer,length=struct.unpack('<3Q',arguments)
                            fd &= 0xffffffff
                            row={'number':4,'args':[fd,buffer,length],
                                 'source':log_pcs[printf_pc]+' hardware breakpoint',
                                 'proc':hex(parsed['X00']),'strings':{}}
                            if fd<=2 and 0<length<=4096:
                                raw=snapshot(buffer,length,'syscall-write.bin')
                                if raw:
                                    row['write_text']=raw.decode('utf-8','replace')
                                    with (OUT/'userspace-live.log').open('a',encoding='utf8') as live:
                                        live.write(row['write_text'])
                            syscalls.append(row)
                            assert len(syscalls)<=options.max_syscalls,'Bounded write trace limit exceeded'
                            assert rsp(f'z1,{printf_pc:x},4')==b'OK'
                            assert rsp('s').startswith((b'T',b'S'))
                            assert rsp(f'Z1,{printf_pc:x},4')==b'OK'
                            qmp('cont')
                            continue
                        if log_pcs[printf_pc]=='_unix_syscall':
                            # XNU8796 generated assym.s: X0=8, X16=136, PC=264.
                            state=snapshot(parsed['X00'],288,'syscall-state.bin')
                            assert state is not None
                            values=struct.unpack_from('<29Q',state,8)
                            number=values[16]&0xffff
                            argv=values[:8] if number else values[1:9]
                            number=number or (values[0]&0xffff)
                            row={'number':number,'args':list(argv),
                                 'user_pc':hex(struct.unpack_from('<Q',state,264)[0]),
                                 'state_header':state[:8].hex(),'strings':{}}
                            for index,value in enumerate(argv):
                                if 0x1000<=value<0x8000000000:
                                    raw=snapshot(value,min(256,4096-(value&4095)),'syscall-user.bin')
                                    if raw and b'\0' in raw:
                                        candidate=raw.split(b'\0')[0]
                                        if candidate and all(32<=c<127 or c in (9,10,13) for c in candidate):
                                            row['strings'][str(index)]=candidate.decode()
                            if number==4 and 0<argv[2]<=4096:
                                raw=snapshot(argv[1],argv[2],'syscall-write.bin')
                                if raw:row['write_text']=raw.decode('utf-8','replace')
                            if number==202 and 0<argv[1]<=24:
                                raw=snapshot(argv[0],argv[1]*4,'syscall-mib.bin')
                                if raw:row['sysctl_mib']=list(struct.unpack('<'+'I'*argv[1],raw))
                            syscalls.append(row)
                            assert len(syscalls)<=options.max_syscalls,'Bounded syscall trace limit exceeded'
                            assert rsp(f'z1,{printf_pc:x},4')==b'OK'
                            assert rsp('s').startswith((b'T',b'S'))
                            assert rsp(f'Z1,{printf_pc:x},4')==b'OK'
                            qmp('cont')
                            continue
                        fmt=snapshot(parsed['X00'],512,'printf-format.bin')
                        stack=snapshot(parsed['SP'],128,'printf-stack.bin')
                        record={'function':log_pcs[printf_pc], 'format':fmt.split(b'\0')[0].decode('utf-8','replace') if fmt else None,
                                'slots':list(struct.unpack('<16Q',stack)) if stack else [],'strings':{},
                                'caller':hex(parsed['X30'])}
                        for index,value in enumerate(record['slots'][:8]):
                            if 0xfffffff000000000 <= value < 0xfffffffffffff000:
                                raw=snapshot(value,256,'printf-string.bin')
                                if raw and b'\0' in raw:
                                    candidate=raw.split(b'\0')[0]
                                    if candidate and all(32<=c<127 or c in (9,10,13) for c in candidate):
                                        record['strings'][str(index)]=candidate.decode()
                        records.append(record)
                        if any(marker in (record.get('format') or '') for marker in
                               ('OdinLegacyGOPDisplay:', 'odin display:', 'CommandWake')):
                            with (OUT/'display-live.jsonl').open('a',encoding='utf8') as live:
                                live.write(json.dumps(record)+'\n')
                        # Observe the first eight actual completed CPU frames.
                        # The guest remains stopped at its own IOLog; save the
                        # scanout as-is, with no second QMP client or guest edit.
                        if 'CPU copied and retired frame %u' in (record.get('format') or ''):
                            ordinal=record['slots'][0]
                            if 1<=ordinal<=8:
                                frame=OUT/f'copied-frame-{ordinal:02}.bin'
                                qmp('human-monitor-command',**{'command-line':
                                    f'pmemsave 0xea600000 10368000 "{frame.as_posix()}"'})
                                if frame.exists() and frame.stat().st_size==10368000:
                                    from PIL import Image
                                    Image.frombytes('RGB',(1080,2400),frame.read_bytes(),
                                        'raw','BGRX').save(frame.with_suffix('.png'))
                        assert len(records)<=10000,'Unexpected printf loop'
                        assert rsp(f'z1,{printf_pc:x},4')==b'OK'
                        assert rsp('s').startswith((b'T',b'S'))
                        assert rsp(f'Z1,{printf_pc:x},4')==b'OK'
                        qmp('cont')
                    (OUT/'printf.json').write_text(json.dumps(records,indent=2)+'\n')
                    if observation_counts:
                        (OUT/'register-observations.json').write_text(json.dumps(dict(
                            scope='Computer-only non-mutating hardware-breakpoint observations',
                            per_address_limit=options.max_observations,
                            counts={hex(at):n for at,n in observation_counts.items()},
                            disabled_at_limit=[hex(at) for at,n in observation_counts.items()
                                               if n==options.max_observations],
                            records=observations),indent=2)+'\n')
                    if options.syscall_log or options.write_log:
                        (OUT/'syscalls.json').write_text(json.dumps(syscalls,indent=2)+'\n')
                    if ui_observer:
                        qmp('stop')
                        capture_ui('ui-thread-snapshot.json')
                    print('Captured native printf calls:',len(records))
            elif options.break_at:
                # Z1 is QEMU's hardware breakpoint, not an instruction patch.
                # Inserting b . into __text itself invalidates the FIPS HMAC.
                with socket.create_connection(('127.0.0.1',ports[1]),timeout=5) as gdb:
                    payload=f'Z1,{symbols[options.break_at]:x},4'.encode()
                    gdb.sendall(b'$'+payload+b'#'+f'{sum(payload)&255:02x}'.encode())
                    response=b''
                    while b'#' not in response:response+=gdb.recv(1024)
                    assert b'$OK#' in response,response
                    gdb.sendall(b'+')
                    qmp('cont');time.sleep(options.seconds)
            else:
                qmp('cont');time.sleep(options.seconds)
            qmp('stop');reply=qmp('human-monitor-command',**{'command-line':'info registers'})
            (OUT/'registers.json').write_text(json.dumps(reply,indent=2)+'\n')
            if options.user_trap_snapshot:
                regs={k:int(v,16) for k,v in re.findall(r'\b(PC|X\d\d|SP)=([0-9a-fA-F]+)',reply.get('return',''))}
                assert regs['PC']==symbols['_handle_breakpoint'], 'Requested user trap not reached'
                state=snapshot(regs['X00'],288,'user-trap-state.bin')
                assert state is not None
                user={f'X{i:02}':v for i,v in enumerate(struct.unpack_from('<29Q',state,8))}
                user.update(FP=struct.unpack_from('<Q',state,240)[0],LR=struct.unpack_from('<Q',state,248)[0],
                            SP=struct.unpack_from('<Q',state,256)[0],PC=struct.unpack_from('<Q',state,264)[0])
                captured={}
                for name in ('X19','X20','X21','X22','X23','X24','X25','X26','FP','SP'):
                    address=user[name]
                    if 0x1000<=address<0x8000000000:
                        length=min(4096 if name=='SP' else 256,4096-(address&4095))
                        data=snapshot(address,length,'user-trap-'+name+'.bin')
                        if data is not None:captured[name]={'address':hex(address),'bytes':len(data)}
                (OUT/'user-trap.json').write_text(json.dumps(dict(saved_state_address=hex(regs['X00']),
                    registers={k:hex(v) for k,v in user.items()},captured=captured),indent=2)+'\n')
            if data_bytes and not options.skip_data_checkpoint:
                # Preserve APFS writes made to guest RAM for offline inspection.
                data_result=qmp('human-monitor-command',**{'command-line':f'pmemsave {data_pa:#x} {data_bytes} "{(OUT / "data-after.apfs").as_posix()}"'})
                assert not data_result.get('error') and data_result.get('return','')=='', data_result
                assert (OUT/'data-after.apfs').stat().st_size==data_bytes, 'Incomplete Data checkpoint; never reuse it'
            (OUT/'registers.json').write_text(json.dumps(reply,indent=2)+'\n')
            qmp('human-monitor-command',**{'command-line':f'pmemsave 0xea600000 10368000 "{(OUT / "framebuffer.bin").as_posix()}"'})
            # Symbol addresses move at each link. The three debug globals are
            # not guaranteed adjacent and debug_buf_size is a 32-bit integer.
            values={}
            for name in ['_debug_buf_base','_debug_buf_ptr','_debug_buf_size']:
                if name not in symbols:continue
                size=4 if name.endswith('_size') else 8
                raw=snapshot(symbols[name],size,name[1:]+'.bin')
                if raw is not None:values[name]=int.from_bytes(raw,'little')
            (OUT/'debug-buf-pointers.json').write_text(json.dumps(values,indent=2)+'\n')
            logbase=values.get('_debug_buf_base',0);logend=values.get('_debug_buf_ptr',0)
            logsize=values.get('_debug_buf_size',0)
            if logbase and logbase<=logend<=logbase+min(logsize,0x100000):
                snapshot(logbase,max(1,logend-logbase),'kernel-debug-buffer.bin')
            # A halt at the native panic funnel preserves the Darwin ABI
            # argument registers before any panic/debugger code can alter them.
            registers=reply.get('return','')
            regs={name:int(value,16) for name,value in re.findall(r'\b(PC|X\d\d|SP)=([0-9a-fA-F]+)',registers)}
            for spec in options.read_register_memory:
                register,length=spec.split(':');length=int(length,0)
                assert register in regs and 0<length<=65536
                snapshot(regs[register],length,'register-memory-'+register+'.bin')
            for spec in options.read_physical_memory:
                address,length=(int(value,0) for value in spec.split(':'))
                assert address>=0 and 0<length<=65536
                target=OUT/f'physical-memory-{address:x}.bin'
                target.unlink(missing_ok=True)
                qmp('human-monitor-command',**{'command-line':f'pmemsave {address:#x} {length} "{target.as_posix()}"'})
            for name in options.read_symbol:
                assert name in symbols,name
                snapshot(symbols[name],64,'symbol-'+name+'.bin')
            if regs.get('PC')==symbols.get('_panic_trap_to_debugger') and '_panic_trap_to_debugger' in (options.halt_at,options.break_at):
                fmt=snapshot(regs['X00'],512,'panic-format.bin')
                va=snapshot(regs['X01'],8,'panic-va-pointer.bin')
                slots=snapshot(int.from_bytes(va,'little'),128,'panic-arguments.bin') if va else None
                panic={'format':fmt.split(b'\0')[0].decode('utf-8','replace') if fmt else None,
                       'slots':list(struct.unpack('<16Q',slots)) if slots else None,
                       'caller':hex(regs['X06']),'scope':'QEMU CPU replay; not device evidence'}
                panic['strings']={}
                for index,value in enumerate(panic['slots'][:8] if panic['slots'] else []):
                    if 0xfffffff000000000<=value<0xfffffffffffff000:
                        raw=snapshot(value,1024,f'panic-string-{index}.bin')
                        if raw and b'\0' in raw:
                            candidate=raw.split(b'\0')[0]
                            if all(32<=c<127 or c in (9,10,13) for c in candidate):
                                panic['strings'][str(index)]=candidate.decode()
                (OUT/'panic.json').write_text(json.dumps(panic,indent=2)+'\n')
                print('CAPTURED PANIC:',json.dumps(panic))
            qmp('quit')
    finally:
        if p.poll() is None:p.terminate()
        p.wait(timeout=10)
data_digest = None
if data_bytes:
    with options.data_ramdisk.open('rb') as data_stream:
        data_digest = hashlib.file_digest(data_stream, 'sha256').hexdigest()
result={'kernel_sha256':hashlib.sha256(b).hexdigest(),'physical_base':hex(physical),
 'source_adt_sha256':source_adt_sha256,'replay_adt_sha256':hashlib.sha256(adt).hexdigest(),
 'qemu_hardware_overlay':options.virt_platform,'qemu_vmm_present':options.qemu_vmm_present,'printf_hardware_trace':options.printf_log,'syscall_record_limit':options.max_syscalls,'syscall_trace_mode':'all' if options.syscall_log else 'write_entries' if options.write_log else None,'ramdisk_bytes':ramdisk_bytes,'owned_memory_size':window,
 'ramdisk_pa':hex(ramdisk_pa) if ramdisk_pa else None,'boot_args':options.boot_args,
 'data_ramdisk_bytes':data_bytes,'data_ramdisk_pa':hex(data_pa) if data_pa else None,
 'data_ramdisk_sha256':data_digest,
 'data_no_sep':options.data_no_sep,
 'data_checkpoint_exported':bool(data_bytes and not options.skip_data_checkpoint),
 'qemu_resident_secondary':options.resident_secondary,
 'host_stop_requested':options.allow_host_stop and (OUT/'stop-request.txt').exists(),
 'trust_cache_sha256':hashlib.sha256(trust_data).hexdigest() if trust_data else None,
 'trust_cache_bytes':len(trust_data),'trust_cache_pa':hex(trust_pa) if trust_pa else None,
 'virtual_base':hex(base),'args':hex(args),'entry_pa':hex(physical+entry-base),'observation_seconds':options.seconds,
 'scope':f'Generic {options.cpu} CPU bootstrap replay only; not SM8350 or iOS qualification',
 'registers':reply}
(OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
trace=(OUT/'trace.log').read_text(errors='replace')
if (options.trampoline or options.resident_secondary) and not options.handoff_only:
    if options.fault_at:
        assert options.fault_handler in symbols
        handler = symbols[options.fault_handler]
        assert f'{physical+handler-base:#x}:' in trace or f'{handler:#x}:' in trace, 'Injected exception did not reach requested handler'
        result.update(injected_fault_at=options.fault_at,early_exception_handler_reached=True)
    else:
        assert f'{symbols["_arm_init"]:#x}:' in trace,'Generic replay did not reach native arm_init'
        result['generic_native_arm_init_reached']=True
    for name,va in symbols.items():
        if name.startswith('_odin_entry_mark') and (not options.fault_at or va<=symbols[options.fault_at]):
            assert f'{physical+va-base:#x}:' in trace, f'Native checkpoint not executed: {name}'
    if options.halt_at:
        assert f'{symbols[options.halt_at]:#x}:' in trace
        result['halted_before_symbol']=options.halt_at
    if options.break_at:
        reached=regs.get('PC')==symbols[options.break_at]
        result['hardware_breakpoint_reached']=reached
        if options.require_breakpoint:assert reached, 'Hardware breakpoint not reached'
        result['hardware_breakpoint_symbol']=options.break_at
        result['integrity_protected_code_changed']=False
    result['native_entry_checkpoint_symbols']={k:v for k,v in symbols.items() if k.startswith(('_odin_','_arm_init'))}
    print('Real assembly replay reached native arm_init; framebuffer may be cleared by the kernel')
if options.handoff_only:
    fb=(OUT/'framebuffer.bin').read_bytes()
    colors=[struct.unpack_from('<I',fb,i*256)[0] for i in range(4)]
    assert colors==[0xff00ff00,0xffffff00,0xff00ffff,0xffffffff],colors
    result.update(handoff_marker_colors=list(map(hex,colors)),native_kernel_run=False)
    print('Real assembly four handoff markers passed',list(map(hex,colors)))
(OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if (OUT/'kernel-debug-buffer.bin').exists():
    print('KERNEL DEBUG BUFFER:',(OUT/'kernel-debug-buffer.bin').read_bytes().decode('utf-8','replace')[-8000:])
print('TRACE TAIL:',trace[-6500:])
