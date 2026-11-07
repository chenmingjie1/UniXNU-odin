// SPDX-License-Identifier: BSD-2-Clause-Patent
// Port of loader-touchrun59's working core0 supervisor / core7 PSCI handoff.
// Keep UniXNU's Mach-O, boot_args and owned RAM; do not ExitBootServices.
#include <Uefi.h>
#include <Protocol/LoadedImage.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include "OdinResident.h"
#include "OdinTouchPower.h"

ODIN_RESIDENT_CONTEXT OdinResidentContext __attribute__((aligned(64)));
STATIC_ASSERT(sizeof(ODIN_RESIDENT_CONTEXT)==128,"Secondary context ABI size");
STATIC_ASSERT(OFFSET_OF(ODIN_RESIDENT_CONTEXT,Entered)==64,"Secondary output cache line");
STATIC_ASSERT(OFFSET_OF(ODIN_RESIDENT_CONTEXT,Mpidr)==112,"Secondary MPIDR assembly offset");
VOID EFIAPI OdinSecondaryEntry(VOID);
INT64 EFIAPI OdinResidentSmc(UINT64 Function, UINT64 Arg1, UINT64 Arg2, UINT64 Arg3);
STATIC EFI_GUID mResidentGuid=ODIN_RESIDENT_PROTOCOL_GUID;
#define SYSREG(Name) ({UINT64 V;__asm__ volatile("mrs %0," #Name:"=r"(V));V;})

STATIC VOID Clean(UINT64 Start,UINT64 Bytes) {
 UINT64 Line=4ULL<<((SYSREG(ctr_el0)>>16)&15),End=Start+Bytes,At=Start&~(Line-1);
 for(;At<End;At+=Line)__asm__ volatile("dc cvac,%0"::"r"(At):"memory");
 __asm__ volatile("dsb sy":::"memory");
}
STATIC BOOLEAN IdentityMapped(UINT64 Address) {
 UINT64 Par;
 __asm__ volatile("at s1e1r,%1\nisb\nmrs %0,par_el1":"=r"(Par):"r"(Address):"memory");
 return !(Par&1) && (Par&0x0000fffffffff000ULL)==(Address&0x0000fffffffff000ULL);
}

EFI_STATUS EFIAPI OdinResidentLaunch(UINT64 Args,UINT64 Entry,UINT64 Memory,UINT64 Used,UINT64 Length,UINT64 VirtualBase) {
 ODIN_RESIDENT_PROTOCOL *Supervisor=NULL;
 EFI_LOADED_IMAGE_PROTOCOL *Image=NULL;
 EFI_PHYSICAL_ADDRESS Stack=0;
 EFI_STATUS Status;
 INT64 Affinity,Result;
 UINT64 Daif,Group;
 EFI_HANDLE *Handles=NULL;UINTN Count=0,Index;
 // Only the actual, validated odin boot arrangement is allowed here.
 if(SYSREG(CurrentEL)!=4 || (SYSREG(mpidr_el1)&0xffffff)!=0 ||
    !Used || Used>Length || Memory+Length<Memory || Args<Memory || Args>=Memory+Used ||
    Entry<Memory || Entry>=Memory+Used)return EFI_UNSUPPORTED;
 Status=gBS->LocateProtocol(&mResidentGuid,NULL,(VOID**)&Supervisor);
 if(EFI_ERROR(Status))return Status;
 if(!Supervisor || Supervisor->Revision!=ODIN_RESIDENT_REVISION || !Supervisor->Run)return EFI_UNSUPPORTED;
 if(!IdentityMapped((UINT64)(UINTN)&OdinSecondaryEntry) ||
    !IdentityMapped((UINT64)(UINTN)&OdinResidentContext) || !IdentityMapped(Memory) ||
    !IdentityMapped(Memory+Used-1))return EFI_UNSUPPORTED;
 Affinity=OdinResidentSmc(0xc4000004,0x700,0,0);
 if(Affinity!=1 && Affinity!=-1)return EFI_ALREADY_STARTED;
 Status=OdinTouchPowerPrepare();
 Print(L"MIX4 touch preparation: %r\r\n",Status);
 Status=gBS->AllocatePages(AllocateAnyPages,EfiLoaderData,4,&Stack);
 if(EFI_ERROR(Status))return Status;
 if(!IdentityMapped(Stack)){gBS->FreePages(Stack,4);return EFI_UNSUPPORTED;}
 // Clean the entire PE image: vectors and secondary entry are executable with
 // MMU/cache off, and their literals may otherwise exist only in BSP cache.
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiLoadedImageProtocolGuid,NULL,&Count,&Handles);
 if(EFI_ERROR(Status)){gBS->FreePages(Stack,4);return Status;}
 for(Index=0;Index<Count;Index++) {
  Status=gBS->HandleProtocol(Handles[Index],&gEfiLoadedImageProtocolGuid,(VOID**)&Image);
  if(!EFI_ERROR(Status) && (UINT64)(UINTN)&OdinSecondaryEntry>=(UINT64)(UINTN)Image->ImageBase &&
     (UINT64)(UINTN)&OdinSecondaryEntry<(UINT64)(UINTN)Image->ImageBase+Image->ImageSize)break;
 }
 gBS->FreePool(Handles);
 if(Index==Count){gBS->FreePages(Stack,4);return EFI_NOT_FOUND;}
 ZeroMem(&OdinResidentContext,sizeof(OdinResidentContext));
 OdinResidentContext.Entry=Entry;OdinResidentContext.Args=Args;
 OdinResidentContext.Sctlr=SYSREG(sctlr_el1);OdinResidentContext.Cpacr=SYSREG(cpacr_el1);
 OdinResidentContext.Stack=Stack+EFI_PAGES_TO_SIZE(4);
 OdinResidentContext.Memory=Memory;OdinResidentContext.Length=Length;OdinResidentContext.VirtualBase=VirtualBase;
 Clean(Memory,Used);
 Clean((UINT64)(UINTN)Image->ImageBase,Image->ImageSize);
 Clean((UINT64)(UINTN)&OdinResidentContext,sizeof(OdinResidentContext));
 Daif=SYSREG(daif);Group=SYSREG(S3_0_C12_C12_7);
 // XNU reprograms the shared GIC. The resident USB path is polling only.
 __asm__ volatile("msr daifset,#15\nmsr S3_0_C12_C12_7,xzr\nisb":::"memory");
 Result=OdinResidentSmc(0xc4000003,0x700,(UINT64)(UINTN)&OdinSecondaryEntry,
                       (UINT64)(UINTN)&OdinResidentContext);
 if(Result!=0) {
  __asm__ volatile("msr S3_0_C12_C12_7,%0\nisb\nmsr daif,%1"::"r"(Group),"r"(Daif):"memory");
  gBS->FreePages(Stack,4);return EFI_DEVICE_ERROR;
 }
 // Ownership commits on CPU_ON success. Even if entry/fault reporting fails,
 // NEVER return to Boot's cleanup, unload this image, or free the RAM window.
 Supervisor->Run(&OdinResidentContext);
 CpuDeadLoop();
 return EFI_ABORTED;
}
