"""QEMU-only core7/HVC bootstrap around the unchanged secondary assembly."""
from pathlib import Path
import subprocess
def stage(out,dev,args,entry):
    root=dev.parents[1];llvm=root/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
    (out/'AsmMacroLib.h').write_text('#define ASM_FUNC(Name) .text ; .globl Name ; .p2align 2 ; Name:\n')
    source=f'''
.text
.global _start
_start:
 msr daifset,#15
 ldr x0,=0x42010000
 mov sp,x0
 adr x19,OdinResidentContext
 ldr x0,={entry:#x}
 str x0,[x19]
 ldr x0,={args:#x}
 str x0,[x19,#8]
 mrs x0,sctlr_el1
 str x0,[x19,#16]
 mrs x0,cpacr_el1
 orr x0,x0,#0x300000
 str x0,[x19,#24]
 ldr x0,=0x42020000
 str x0,[x19,#32]
 ldr x0,=0xc4000003
 mov x1,#7
 adr x2,OdinSecondaryEntry
 mov x3,x19
 hvc #0
 str x0,[x19,#128]
1: wfe
 b 1b
.data
.balign 64
.global OdinResidentContext
OdinResidentContext: .zero 192
'''
    (out/'resident.S').write_text(source)
    (out/'resident.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x41000000; .text : { *(.text*) } .data : { *(.data*) } }\n')
    commands=[]
    def run(command):
        commands.append(list(map(str,command)))
        p=subprocess.run(list(map(str,command)),capture_output=True,text=True)
        assert p.returncode==0,p.stdout+p.stderr
    for name,src in [('resident',out/'resident.S'),('secondary',dev/'firmware/OdinSecondary.S')]:
        run([llvm/'clang.exe','--target=aarch64-none-elf','-I',out,'-c',src,'-o',out/(name+'.o')])
    run([llvm/'ld.lld.exe','-flavor','gnu','-m','aarch64elf','-T',out/'resident.ld',out/'resident.o',out/'secondary.o','-o',out/'resident.elf'])
    run([llvm/'llvm-objcopy.exe','-O','binary',out/'resident.elf',out/'entry.bin'])
    return commands
