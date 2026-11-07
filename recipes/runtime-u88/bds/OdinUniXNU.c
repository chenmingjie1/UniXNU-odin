// SPDX-License-Identifier: MIT
// u05 diagnostic: retain EFI handoff errors and initrd provider telemetry.
#include <Uefi.h>
#include <Pi/PiFirmwareFile.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/GraphicsOutput.h>
#include <Library/DxeServicesLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL *mGop;
STATIC EFI_STATUS mStatus[8];
STATIC UINTN mCount;
STATIC EFI_GUID mRamDiagGuid={0x71b5b2d3,0xe375,0x446a,{0x93,0x18,0x0d,0x14,0x49,0x69,0xa5,0x05}};
STATIC CONST UINT8 mDigits[16][5] = {
 {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},
 {0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},
 {0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
 {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},
 {0x36,0x49,0x49,0x49,0x36},{6,0x49,0x49,0x29,0x1e},
 {0x7e,0x11,0x11,0x11,0x7e},{0x7f,0x49,0x49,0x49,0x36},
 {0x3e,0x41,0x41,0x41,0x22},{0x7f,0x41,0x41,0x22,0x1c},
 {0x7f,0x49,0x49,0x49,0x41},{0x7f,9,9,9,1}
};

STATIC VOID Hex(UINT64 Value, UINTN Digits, UINTN X, UINTN Y) {
 UINTN i,x,y; EFI_GRAPHICS_OUTPUT_BLT_PIXEL White={255,255,255,0};
 for(i=0;i<Digits;i++) {
  UINTN digit=(UINTN)((Value>>((Digits-i-1)*4))&15);
  for(x=0;x<5;x++) for(y=0;y<7;y++) if(mDigits[digit][x]&(1U<<y))
   mGop->Blt(mGop,&White,EfiBltVideoFill,0,0,X+i*18+x*3,Y+y*3,3,3,0);
 }
}

STATIC VOID Draw(VOID) {
 UINTN i; UINT64 *Ram=NULL; EFI_GRAPHICS_OUTPUT_BLT_PIXEL Black={0,0,0,0};
 if(EFI_ERROR(gBS->LocateProtocol(&gEfiGraphicsOutputProtocolGuid,NULL,(VOID**)&mGop)))return;
 if(mGop->Mode==NULL || mGop->Mode->Info==NULL ||
    mGop->Mode->Info->HorizontalResolution<420 || mGop->Mode->Info->VerticalResolution<680)return;
 mGop->Blt(mGop,&Black,EfiBltVideoFill,0,0,0,0,420,680,0);
 AsciiPrintXY(12,8,NULL,NULL,"UniXNU u65 / USB desktop");
 for(i=0;i<mCount;i++) {
  Hex(0x0400+i,4,12,42+i*34);
  Hex((UINT64)mStatus[i],16,102,42+i*34);
 }
 if(!EFI_ERROR(gBS->LocateProtocol(&mRamDiagGuid,NULL,(VOID**)&Ram)) && Ram[0]==1) {
  for(i=0;i<9;i++) {Hex(0xd000+i,4,12,320+i*34);Hex(Ram[i],16,102,320+i*34);}
 } else {Hex(0xd000,4,12,320);Hex(EFI_NOT_FOUND,16,102,320);}
}

STATIC VOID Record(EFI_STATUS Status) {
 if(mCount<8)mStatus[mCount++]=Status;
 Draw();
}

EFI_STATUS EFIAPI OdinRemoteMediaEntry(EFI_HANDLE,EFI_SYSTEM_TABLE*);
EFI_STATUS OdinRemoteHandshake(VOID);
EFI_STATUS OdinRemoteInstallLoaderGuard(VOID);
VOID OdinRemoteBootStatus(CONST CHAR8*,EFI_STATUS);
VOID OdinRemoteRecovery(VOID);
VOID OdinRunDiagnostic(VOID) {
 STATIC CONST EFI_GUID File={0x9b665204,0xa133,0x47a2,{0x93,0x96,0x9e,0x2b,0x37,0x0a,0x4e,0x25}};
 STATIC CHAR16 Marker[]=L"unixnu:firmware";
 EFI_STATUS Status; EFI_HANDLE Image=NULL; VOID *Buffer=NULL; UINTN Size=0;
 EFI_LOADED_IMAGE_PROTOCOL *Loaded=NULL;
 Status=gBS->SetWatchdogTimer(0,0,0,NULL);
 if(EFI_ERROR(Status)){Record(Status);goto Hold;}
 Status=OdinRemoteMediaEntry(gImageHandle,gST);Record(Status);
 if(EFI_ERROR(mStatus[0]))goto Hold;
 Status=OdinRemoteHandshake();Record(Status);
 if(EFI_ERROR(mStatus[1]))goto Hold;
 // This diagnostic must retain a returned error until the user recovers it.
 Record(gBS->SetWatchdogTimer(0,0,0,NULL));                       // 0400
 Status=GetSectionFromAnyFv(&File,EFI_SECTION_PE32,0,&Buffer,&Size);
 Record(Status);                                               // 0401
 if(EFI_ERROR(Status))goto Hold;
 Status=gBS->LoadImage(FALSE,gImageHandle,NULL,Buffer,Size,&Image);
 FreePool(Buffer);Record(Status);                              // 0402
 if(EFI_ERROR(Status))goto Hold;
 Status=gBS->HandleProtocol(Image,&gEfiLoadedImageProtocolGuid,(VOID**)&Loaded);
 Record(Status);                                               // 0403
 if(EFI_ERROR(Status))goto Hold;
 Loaded->LoadOptions=Marker;Loaded->LoadOptionsSize=sizeof(Marker);
 Record(EFI_SUCCESS);                                          // 0404: before StartImage
 Status=OdinRemoteInstallLoaderGuard();
 OdinRemoteBootStatus("loader-guard",Status);
 if(EFI_ERROR(Status))goto Hold;
 Status=gBS->StartImage(Image,NULL,NULL);
 OdinRemoteBootStatus("manager-return",Status);
 Record(Status);                                               // 0405: StartImage returned
 Record(gBS->UnloadImage(Image));                               // 0406
Hold:
 OdinRemoteBootStatus("bds-return",Status);
 Print(L"UniXNU u05 handoff stopped. Retaining EFI/initrd status; manual recovery required.\r\n");
 Draw();
 OdinRemoteRecovery();
 for(;;)gBS->Stall(1000000);
}
