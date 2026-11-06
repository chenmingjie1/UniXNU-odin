// SPDX-License-Identifier: MIT
// Accept a direct FAT or a prefix from an exact backed-up odin vendor ramdisk.
#include "OdinVendorPrefixes.h"

STATIC BOOLEAN OdinFatSize(CONST UINT8 *Data, UINT64 Available, UINT64 *Bytes) {
 UINT32 Sectors;
 if(Available<512 || Data[510]!=0x55 || Data[511]!=0xaa || Data[11]!=0 || Data[12]!=2)return FALSE;
 Sectors=(UINT32)Data[19]|((UINT32)Data[20]<<8);
 if(Sectors==0)Sectors=(UINT32)Data[32]|((UINT32)Data[33]<<8)|((UINT32)Data[34]<<16)|((UINT32)Data[35]<<24);
 *Bytes=(UINT64)Sectors*512;
 return *Bytes>=512 && *Bytes<=Available;
}

STATIC EFI_STATUS OdinSelectInitrd(UINT64 *Start, UINT64 End, UINT64 *Bytes, UINT64 *Skipped) {
 UINTN i,j; UINT32 Crc; UINT64 Offset; CONST UINT8 *First;
 *Bytes=0;*Skipped=0;
 if(End<=*Start)return EFI_COMPROMISED_DATA;
 First=(CONST UINT8 *)(UINTN)*Start;
 if(OdinFatSize(First,End-*Start,Bytes))return EFI_SUCCESS;
 for(i=0;i<sizeof(mOdinPrefixes)/sizeof(mOdinPrefixes[0]);i++) {
  if(End-*Start < mOdinPrefixes[i].Bytes+512)continue;
  if(EFI_ERROR(gBS->CalculateCrc32((VOID *)First,(UINTN)mOdinPrefixes[i].Bytes,&Crc)) || Crc!=mOdinPrefixes[i].Crc)continue;
  // Both tightly concatenated and page-aligned bootloader layouts are bounded.
  for(j=0;j<2;j++) {
   Offset=j==0?mOdinPrefixes[i].Bytes:mOdinPrefixes[i].PaddedBytes;
   if(Offset>End-*Start || !OdinFatSize(First+Offset,End-*Start-Offset,Bytes))continue;
   *Start+=Offset;*Skipped=Offset;return EFI_SUCCESS;
  }
 }
 *Bytes=0;return EFI_NOT_FOUND;
}
