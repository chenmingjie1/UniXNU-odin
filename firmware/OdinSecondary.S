// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <AsmMacroLib.h>
ASM_FUNC(OdinResidentSmc)
 smc #0
 ret

// PSCI delivers the physical shared context in x0, MMU and cache disabled.
ASM_FUNC(OdinSecondaryEntry)
 msr daifset,#15
 adrp x9,OdinSecondaryVectors
 add x9,x9,:lo12:OdinSecondaryVectors
 msr vbar_el1,x9
 ldr x9,[x0,#24]
 msr cpacr_el1,x9
 ldr x9,[x0,#16]
 bic x9,x9,#1
 bic x9,x9,#4
 bic x9,x9,#0x1000
 msr sctlr_el1,x9
 isb
 ic iallu
 dsb sy
 isb
 ldr x9,[x0,#32]
 mov sp,x9
 mrs x9,midr_el1
 str x9,[x0,#104]
 mrs x9,mpidr_el1
 str x9,[x0,#112]
 mov x9,#1
 str x9,[x0,#64]
 dsb sy
 sev
 ldp x9,x10,[x0]
 mov x0,x10
 adr x30,OdinSecondaryReturned
 br x9
OdinSecondaryReturned:
 mov x9,#2
 b OdinSecondaryFaultStore
OdinSecondaryFault:
 mov x9,#1
OdinSecondaryFaultStore:
 adrp x10,OdinResidentContext
 add x10,x10,:lo12:OdinResidentContext
 str x9,[x10,#72]
 mrs x9,esr_el1
 str x9,[x10,#80]
 mrs x9,elr_el1
 str x9,[x10,#88]
 mrs x9,far_el1
 str x9,[x10,#96]
 dsb sy
 sev
 // No return into firmware and no normal-path halt before the kernel branch.
1: wfe
 b 1b
.p2align 11
OdinSecondaryVectors:
.rept 16
 b OdinSecondaryFault
 .p2align 7
.endr
