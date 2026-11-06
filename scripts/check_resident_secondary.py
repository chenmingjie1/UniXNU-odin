"""Execute the production secondary assembly on QEMU's PSCI SMP implementation.

QEMU uses its own CPU affinities and HVC, not odin's 0x700/SMC. This verifies
the shared context, boot argument ABI and concurrent BSP residency only.
"""
from pathlib import Path
import hashlib,json,socket,struct,subprocess,time
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
OUT=DEV/'build/resident-secondary-u69';OUT.mkdir(exist_ok=True)
BIN=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
(OUT/'AsmMacroLib.h').write_text('#define ASM_FUNC(Name) .text ; .globl Name ; .p2align 2 ; Name:\n')
# Only the harness has HVC. The production assembly is compiled unchanged.
source=r'''
.text
.global _start
_start:
 msr daifset,#15
 ldr x0,=0x42010000
 mov sp,x0
 adr x19,OdinResidentContext
 adr x0,fake_kernel
 str x0,[x19]
 ldr x0,=0x1234abcd
 str x0,[x19,#8]
 mrs x0,sctlr_el1
 str x0,[x19,#16]
 mrs x0,cpacr_el1
 str x0,[x19,#24]
 ldr x0,=0x42020000
 str x0,[x19,#32]
 // Try the two standard QEMU CPU affinity layouts; never change phone code.
 mov x20,#7
1:
 ldr x0,=0xc4000003
 mov x1,x20
 adr x2,OdinSecondaryEntry
 mov x3,x19
 hvc #0
 cbz x0,2f
 cmp x20,#7
 b.ne failure
 mov x20,#0x700
 b 1b
2:
 str x20,[x19,#176]
 mov x21,#0
3:
 add x21,x21,#1
 str x21,[x19,#160]
 dsb sy
 ldr x0,[x19,#128]
 cbz x0,3b
 ldr x0,=0x51cc355
 str x0,[x19,#168]
 dsb sy
4: wfe
 b 4b
failure:
 str x0,[x19,#184]
 b 4b
fake_kernel:
 adr x10,OdinResidentContext
 str x0,[x10,#136]
 mrs x11,mpidr_el1
 str x11,[x10,#144]
 mrs x11,sctlr_el1
 str x11,[x10,#152]
 ldr x11,[x10,#160]
5:
 ldr x12,[x10,#160]
 cmp x11,x12
 b.eq 5b
 mov x11,#1
 str x11,[x10,#128]
 dsb sy
6: wfe
 b 6b
.data
.balign 64
.global OdinResidentContext
OdinResidentContext: .zero 192
'''
(OUT/'harness.S').write_text(source)
(OUT/'link.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x41000000; .text : { *(.text*) } .data : { *(.data*) } }\n')
commands=[]
def run(cmd):
    commands.append(list(map(str,cmd)))
    r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True)
    assert not r.returncode,r.stdout+r.stderr
for name,src in [('secondary',DEV/'firmware/OdinSecondary.S'),('harness',OUT/'harness.S')]:
    run([BIN/'clang.exe','--target=aarch64-none-elf','-I',OUT,'-c',src,'-o',OUT/(name+'.o')])
run([BIN/'ld.lld.exe','-flavor','gnu','-m','aarch64elf','-T',OUT/'link.ld',OUT/'harness.o',OUT/'secondary.o','-o',OUT/'harness.elf'])
run([BIN/'llvm-objcopy.exe','-O','binary',OUT/'harness.elf',OUT/'harness.bin'])
symbols=subprocess.run([str(BIN/'llvm-nm.exe'),str(OUT/'harness.elf')],capture_output=True,text=True,check=True).stdout
context=int(next(line.split()[0] for line in symbols.splitlines() if line.endswith(' OdinResidentContext')),16)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
cmd=[ROOT/'work/odin-portable-linux/qemu/qemu-system-aarch64.exe','-machine','virt,virtualization=off,gic-version=3',
     '-cpu','cortex-a76','-accel','tcg','-m','256','-smp','8','-display','none','-serial','none','-net','none',
     '-device',f'loader,file={OUT / "harness.bin"},addr=0x41000000,cpu-num=0,force-raw=on',
     '-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off','-no-reboot','-S']
commands.append(list(map(str,cmd)))
with (OUT/'qemu.log').open('wb') as log:
    proc=subprocess.Popen(list(map(str,cmd)),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+10
        while True:
            try:s=socket.create_connection(('127.0.0.1',port),timeout=1);break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        with s:
            f=s.makefile('rwb',buffering=0);json.loads(f.readline())
            def qmp(name,args=None):
                f.write((json.dumps(dict(execute=name,**({'arguments':args} if args else {})))+'\n').encode())
                while True:
                    reply=json.loads(f.readline())
                    if 'event' in reply:continue
                    assert 'error' not in reply,reply
                    return reply.get('return')
            qmp('qmp_capabilities');qmp('cont');time.sleep(1);qmp('stop')
            dump=OUT/'context.bin'
            qmp('human-monitor-command',dict(**{'command-line':f'pmemsave {context:#x} 192 "{dump.as_posix()}"'}))
            values=struct.unpack('<24Q',dump.read_bytes())
            report=dict(secondary_entered=values[8]==1,fault=values[9],kernel_entry_called=values[16]==1,
                boot_args_preserved=values[17]==0x1234abcd,secondary_mpidr=hex(values[18]),
                mmu_cache_off=(values[19]&0x1005)==0,bsp_iterations=values[20],
                bsp_and_kernel_concurrent=values[21]==0x51cc355,psci_target=hex(values[22]),psci_failure=hex(values[23]),
                production_secondary_sha256=hashlib.sha256((DEV/'firmware/OdinSecondary.S').read_bytes()).hexdigest(),
                phone_tested=False,scope='QEMU CPU affinity/HVC only; physical 0x700/SMC and vendor USB not qualified')
            report['passed']=all(report[k] for k in ('secondary_entered','kernel_entry_called','boot_args_preserved','mmu_cache_off','bsp_and_kernel_concurrent')) and not report['fault']
            (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
            (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
            print(json.dumps(report,indent=2));assert report['passed']
            qmp('quit')
    finally:
        if proc.poll() is None:proc.kill()
        proc.wait(timeout=10)
