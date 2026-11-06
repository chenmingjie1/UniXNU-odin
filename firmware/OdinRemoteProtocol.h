// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef ODIN_REMOTE_PROTOCOL_H
#define ODIN_REMOTE_PROTOCOL_H
STATIC EFI_STATUS OdinValidateResponse(CONST UINT8 *Input,UINTN Bytes,UINT32 Sequence,
                                      UINT32 FileId,UINT64 Offset,UINTN Wanted) {
 UINT32 crc;EFI_STATUS s;
 if(!Input || !Wanted || Wanted>SIZE_1MB || Bytes!=Wanted+32)return EFI_BAD_BUFFER_SIZE;
 if(CompareMem(Input,"ODNRD001",8) || ReadUnaligned32((CONST UINT32*)(Input+8))!=Sequence ||
    ReadUnaligned32((CONST UINT32*)(Input+12))!=FileId ||
    ReadUnaligned64((CONST UINT64*)(Input+16))!=Offset ||
    ReadUnaligned32((CONST UINT32*)(Input+24))!=Wanted)return EFI_COMPROMISED_DATA;
 s=gBS->CalculateCrc32((VOID*)(Input+32),Wanted,&crc);if(EFI_ERROR(s))return s;
 return crc==ReadUnaligned32((CONST UINT32*)(Input+28))?EFI_SUCCESS:EFI_CRC_ERROR;
}
#endif
