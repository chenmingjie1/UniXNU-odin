// ODIN_MMU_DIAGNOSTICS: transient, stackless early-boot diagnostics.
// The framebuffer is mapped as normal non-cacheable memory, identity, in
// previously EMPTY L2 slots only. No existing RAM mapping is replaced.
// x8 is reserved for the caller's saved LR in the hex renderer.
.macro odin_hex_sysreg reg, row, label
 mrs x0, \reg
 mov x1, #\row
 mov x2, #\label
 mov x3, x20
 mov x8, lr
 bl EXT(odin_hex_row)
 mov lr, x8
.endm

.p2align 2
.globl EXT(odin_hex_row)
LEXT(odin_hex_row)
 // x0=value, x1=row, x2=16-bit label, x3=boot_args physical/KVA.
 // Uses x0-x7,x9-x18 only; no stack and no nested calls.
 ldr x4, [x3, #0x28]
 ldr x5, [x3, #0x38]
 lsl x1, x1, #5
 add x1, x1, #128
 madd x6, x1, x5, x4
 add x6, x6, #64
 mov x7, #0
1:
 cmp x7, #4
 b.hs 2f
 ubfx x10, x2, #12, #4
 lsl x2, x2, #4
 b 3f
2:
 lsr x10, x0, #60
 lsl x0, x0, #4
3:
 adrp x9, Lodin_hex_font@page
 add x9, x9, Lodin_hex_font@pageoff
 add x9, x9, x10, lsl #3
 mov x11, #0
4:
 ldrb w12, [x9, x11]
 mov x15, #0
5:
 add x10, x11, x11, lsl #1
 add x10, x10, x15
 madd x14, x10, x5, x6
 mov x13, #4
6:
 lsr w10, w12, w13
 and w10, w10, #1
 neg w17, w10
 orr w17, w17, #0xff000000
 mov x16, #3
7:
 str w17, [x14], #4
 subs x16, x16, #1
 b.ne 7b
 subs x13, x13, #1
 b.pl 6b
 add x15, x15, #1
 cmp x15, #3
 b.lo 5b
 add x11, x11, #1
 cmp x11, #8
 b.lo 4b
 add x6, x6, #72
 add x7, x7, #1
 cmp x7, #4
 b.ne 8f
 add x6, x6, #72
8:
 cmp x7, #20
 b.lo 1b
 dsb sy
 ret
.p2align 2
Lodin_hex_font:
 .byte 14,17,19,21,25,17,14,0
 .byte 4,12,4,4,4,4,14,0
 .byte 14,17,1,2,4,8,31,0
 .byte 30,1,1,14,1,1,30,0
 .byte 2,6,10,18,31,2,2,0
 .byte 31,16,16,30,1,1,30,0
 .byte 14,16,16,30,17,17,14,0
 .byte 31,1,2,4,8,8,8,0
 .byte 14,17,17,14,17,17,14,0
 .byte 14,17,17,15,1,1,14,0
 .byte 14,17,17,31,17,17,17,0
 .byte 30,17,17,30,17,17,30,0
 .byte 14,17,16,16,16,17,14,0
 .byte 30,17,17,17,17,17,30,0
 .byte 31,16,16,30,16,16,31,0
 .byte 31,16,16,30,16,16,16,0

.p2align 2
.globl EXT(odin_early_exception)
LEXT(odin_early_exception)
 // Low vectors and this handler execute through V=P, even after MMU on.
 // Terminal handler only. Restore neither the exception nor the OS run.
 mrs x19, ESR_EL1
 mrs x21, ELR_EL1
 mrs x22, FAR_EL1
 mrs x23, SCTLR_EL1
 mrs x24, SPSR_EL1
 mrs x25, TCR_EL1
 msr DAIFSet, #15
 dsb sy
 bic x0, x23, #1
 bic x0, x0, #4
 bic x0, x0, #0x1000
 msr SCTLR_EL1, x0
 isb
 adrp x9, EXT(odin_diag_bootargs)@page
 add x9, x9, EXT(odin_diag_bootargs)@pageoff
 ldr x20, [x9]
 cbz x20, Lodin_diag_stop
 // These six rows replace the pre-MMU state, carrying unmodified registers.
 mov x0, x19
 mov x1, #8
 mov x2, #0xe000
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x21
 mov x1, #9
 mov x2, #0xe001
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x22
 mov x1, #10
 mov x2, #0xe002
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x23
 mov x1, #11
 mov x2, #0xe003
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x24
 mov x1, #12
 mov x2, #0xe004
 mov x3, x20
 bl EXT(odin_hex_row)
 mov x0, x25
 mov x1, #13
 mov x2, #0xe005
 mov x3, x20
 bl EXT(odin_hex_row)
Lodin_diag_stop:
 b Lodin_diag_stop

// Callable only before PE_init_platform changes the virtual memory setup.
.macro odin_c_checkpoint name, index, lo, hi
 .globl EXT(\name)
LEXT(\name)
 odin_kernel_mark x0, \index, \lo, \hi
 ret
.endm
odin_c_checkpoint odin_c_entry, 7, 0xffff, 0xff00
odin_c_checkpoint odin_c_presign, 8, 0x8000, 0xff80
odin_c_checkpoint odin_c_rebase, 9, 0x80ff, 0xffff
odin_c_checkpoint odin_c_cpudata, 10, 0xff80, 0xffff

.globl EXT(odin_c_platform)
LEXT(odin_c_platform)
 // Restore Apple's normal KVA exception vectors before platform init.
 // The call remains immediately BEFORE PE_init_platform, so diagnostic
 // framebuffer mappings still exist and BootArgs has already been copied.
 odin_kernel_mark x0, 11, 0xffff, 0xff80
 adrp x9, EXT(odin_diag_saved_vbar)@page
 add x9, x9, EXT(odin_diag_saved_vbar)@pageoff
 ldr x9, [x9]
 msr VBAR_EL1, x9
 isb
 ret

.data
.p2align 3
.globl EXT(odin_diag_bootargs)
LEXT(odin_diag_bootargs)
 .quad 0
.globl EXT(odin_diag_saved_vbar)
LEXT(odin_diag_saved_vbar)
 .quad 0
.text
