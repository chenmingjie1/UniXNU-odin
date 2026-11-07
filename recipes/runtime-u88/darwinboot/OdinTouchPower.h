// SPDX-License-Identifier: BSD-2-Clause-Patent
// Same board requests and GPIO sequence as verified HakiOS r56-r64.
// Called on the firmware CPU before native XNU begins. No reset from XNU.
#include <Protocol/LoadedImage.h>
#include <Library/UefiLib.h>
#include "OdinTouchRpmhFingerprint.h"
STATIC BOOLEAN OdinTouchCompare(UINT64 Base,UINT32 Start,UINT32 Bytes,CONST UINT8 *Expected,CONST UINT32 *Rel) {
 CONST UINT8 *Live=(CONST VOID*)(UINTN)(Base+Start);UINT32 R=0;
 for(UINT32 I=0;I<Bytes;I++) {
  if(I==Rel[R]) {
   UINT64 Value=ReadUnaligned64((CONST VOID*)(Live+I)),Old=ReadUnaligned64((CONST VOID*)(Expected+I));
   if(Value<Base||Value-Base!=Old)return FALSE;
   I+=7;R++;
  }else if(Live[I]!=Expected[I])return FALSE;
 }
 return Rel[R]==0xffffffffU;
}
STATIC BOOLEAN OdinTouchMapped(UINT64 Address) {
 UINT64 Par;__asm__ volatile("at s1e1r,%1\nisb\nmrs %0,par_el1":"=r"(Par):"r"(Address):"memory");
 return !(Par&1)&&(Par&0x0000fffffffff000ULL)==(Address&0x0000fffffffff000ULL);
}
STATIC UINT32 OdinTouchRead(UINT64 Address){return *(volatile UINT32*)(UINTN)Address;}
STATIC VOID OdinTouchWrite(UINT64 Address,UINT32 Value) {
 *(volatile UINT32*)(UINTN)Address=Value;__asm__ volatile("dsb sy":::"memory");
}
STATIC EFI_STATUS OdinTouchPowerPrepare(VOID) {
 STATIC EFI_GUID Guid={0xe1d0b573,0xf29f,0x495d,{0x93,0x52,0xca,0x0d,0xd4,0x2a,0x0a,0x74}};
 STATIC CONST UINT32 Rvas[]={0x15a0,0x15b8,0x15f4,0x1630,0x1674,0x16b8,0x16fc,0x1714,0x172c,0x1744,0x1780,0x1798,0x17b0,0x17c8,0x17e0,0x1824,0x183c,0x1854,0x185c,0x1898,0x18b0,0x14b0,0x18c8,0x18d0};
 VOID *Protocol=NULL,*Handle=NULL;UINT64 *Slots,Base;EFI_STATUS Status;
 Status=gBS->LocateProtocol(&Guid,NULL,&Protocol);if(EFI_ERROR(Status)||!Protocol)return EFI_NOT_FOUND;
 Slots=Protocol;if(Slots[0]!=0x10001||Slots[1]<0x15a0)return EFI_UNSUPPORTED;
 Base=Slots[1]-0x15a0;if((UINT64)(UINTN)Protocol!=Base+0xe0d8)return EFI_UNSUPPORTED;
 for(UINT32 I=0;I<24;I++)if(Slots[I+1]!=Base+Rvas[I])return EFI_UNSUPPORTED;
 if(!OdinTouchMapped(Base)||!OdinTouchMapped(Base+0x12fff)||
  !OdinTouchCompare(Base,4096,53248,odin_rpmh_fp_2_1000,odin_rpmh_fp_2_1000_rel)||
  !OdinTouchCompare(Base,65536,10204,odin_rpmh_fp_2_10000,odin_rpmh_fp_2_10000_rel))return EFI_SECURITY_VIOLATION;
 // Validate the command database resource used by the original board driver.
 CONST UINT8 *Db=(CONST VOID*)(UINTN)0x80860000;UINT32 Matches=0;
 if(!OdinTouchMapped((UINT64)(UINTN)Db)||ReadUnaligned32((CONST VOID*)(Db+4))!=0x0c0330db)return EFI_UNSUPPORTED;
 for(UINT32 S=0;S<8;S++) {
  CONST UINT8 *H=Db+8+16*S;UINT16 Slave=ReadUnaligned16(H),Off=ReadUnaligned16(H+2),Data=ReadUnaligned16(H+4),Count=ReadUnaligned16(H+6);
  if(!Slave)continue;
  if(Count>512||144U+Off+24U*Count>0x20000U)return EFI_COMPROMISED_DATA;
  for(UINT32 I=0;I<Count;I++) {
   CONST UINT8 *E=Db+144+Off+24*I;
   if(CompareMem(E,"ldoc2\0\0\0",8))continue;
   UINT16 Len=ReadUnaligned16(E+20),Aux=ReadUnaligned16(E+22);
   if(Slave!=4||ReadUnaligned16(H+8)!=0x100||ReadUnaligned32(E+16)!=0x42600||Len!=4||144U+Data+Aux+4>0x20000U||ReadUnaligned32(Db+144+Data+Aux)!=1)return EFI_UNSUPPORTED;
   Matches++;
  }
 }
 if(Matches!=1)return EFI_NOT_FOUND;
 Print(L"MIX4 touch: retained board VDD 1.8V + reset sequence\r\n");
 typedef EFI_STATUS (EFIAPI *CREATE)(UINT32,CONST CHAR8*,VOID**);
 typedef EFI_STATUS (EFIAPI *ISSUE)(VOID*,UINT32,UINT8,UINT32,UINT32,UINT32*);
 Status=((CREATE)(UINTN)Slots[5])(2,"odin-unixnu-touch",&Handle);
 if(EFI_ERROR(Status)||!Handle)return EFI_DEVICE_ERROR;
 STATIC CONST UINT32 Address[3]={0x42600,0x42608,0x42604},Value[3]={1800,7,1};
 for(UINT32 I=0;I<3;I++) {
  UINT32 Request=0xffffffff;Status=((ISSUE)(UINTN)Slots[19])(Handle,0,1,Address[I],Value[I],&Request);
  if(EFI_ERROR(Status)||!Request||Request==0xffffffff)return EFI_DEVICE_ERROR;
 }
 UINT64 Reset=0x0f116000,Avdd=0x0f184000;
 if(!OdinTouchMapped(Reset)||!OdinTouchMapped(Avdd))return EFI_UNSUPPORTED;
 UINT32 ResetCfg=(OdinTouchRead(Reset)&~0x3cU)|0x200U,AvddCfg=(OdinTouchRead(Avdd)&~0x3cU)|0x200U;
 OdinTouchWrite(Reset+4,0);OdinTouchWrite(Reset,ResetCfg);gBS->Stall(10000);
 OdinTouchWrite(Avdd+4,2);OdinTouchWrite(Avdd,AvddCfg);gBS->Stall(15000);
 OdinTouchWrite(Reset+4,2);gBS->Stall(100000);
 if(OdinTouchRead(Reset)!=ResetCfg||OdinTouchRead(Avdd)!=AvddCfg||!(OdinTouchRead(Reset+4)&2)||!(OdinTouchRead(Avdd+4)&2))return EFI_DEVICE_ERROR;
 return EFI_SUCCESS;
}
