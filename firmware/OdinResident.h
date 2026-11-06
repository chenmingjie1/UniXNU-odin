// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef ODIN_RESIDENT_H
#define ODIN_RESIDENT_H
#define ODIN_RESIDENT_PROTOCOL_GUID \
 {0x4cd9357a,0xa9b2,0x445b,{0x8b,0xc2,0x71,0x34,0x6a,0x72,0x69,0x09}}
#define ODIN_RESIDENT_REVISION 1
// Separate cache lines for immutable launch input and secondary-written output.
// This memory and the loader image remain allocated for the entire kernel run.
typedef struct {
 UINT64 Entry, Args, Sctlr, Cpacr, Stack, Memory, Length, VirtualBase;
 volatile UINT64 Entered, Fault, Esr, Elr, Far, Midr, Mpidr, Spare;
} ODIN_RESIDENT_CONTEXT;
typedef struct {
 UINT64 Revision;
 VOID (EFIAPI *Run)(ODIN_RESIDENT_CONTEXT *Context);
} ODIN_RESIDENT_PROTOCOL;
EFI_STATUS EFIAPI OdinResidentLaunch(UINT64 Args, UINT64 Entry, UINT64 Memory, UINT64 Used, UINT64 Length, UINT64 VirtualBase);
#endif
