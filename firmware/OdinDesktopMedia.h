// SPDX-License-Identifier: BSD-2-Clause-Patent
// Raw, read-only media input. The destination must already be inside the
// loader's allocated window. No full-sized temporary pool allocation is made.
#ifndef ODIN_DESKTOP_MEDIA_H
#define ODIN_DESKTOP_MEDIA_H
STATIC EFI_STATUS
OdinOpenMedia (EFI_FILE_PROTOCOL *Root, CONST CHAR16 *Path, UINTN Limit,
               EFI_FILE_PROTOCOL **File, UINTN *Bytes)
{
  EFI_STATUS Status;
  EFI_FILE_INFO *Info = NULL;
  UINTN InfoSize = 0;
  *File = NULL; *Bytes = 0;
  Status = Root->Open (Root, File, (CHAR16 *)Path, EFI_FILE_MODE_READ, 0);
  if (EFI_ERROR (Status)) { *File = NULL; return Status; }
  Status = (*File)->GetInfo (*File, &gEfiFileInfoGuid, &InfoSize, NULL);
  if (Status != EFI_BUFFER_TOO_SMALL) { Status = EFI_DEVICE_ERROR; goto Done; }
  if ((InfoSize < SIZE_OF_EFI_FILE_INFO) || (InfoSize > 65536)) { Status = EFI_BAD_BUFFER_SIZE; goto Done; }
  Info = AllocatePool (InfoSize);
  if (Info == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Done; }
  Status = (*File)->GetInfo (*File, &gEfiFileInfoGuid, &InfoSize, Info);
  if (EFI_ERROR (Status)) { goto Done; }
  if (InfoSize < SIZE_OF_EFI_FILE_INFO) { Status = EFI_DEVICE_ERROR; goto Done; }
  if ((Info->Attribute & EFI_FILE_DIRECTORY) || (Info->FileSize == 0) ||
      (Info->FileSize > Limit) || (Info->FileSize & (EFI_PAGE_SIZE - 1))) {
    Status = EFI_BAD_BUFFER_SIZE; goto Done;
  }
  *Bytes = (UINTN)Info->FileSize;
Done:
  if (Info != NULL) { FreePool (Info); }
  if (EFI_ERROR (Status)) { (*File)->Close (*File); *File = NULL; *Bytes = 0; }
  return Status;
}

STATIC EFI_STATUS
OdinReadMedia (EFI_FILE_PROTOCOL *File, VOID *Destination, UINTN Bytes)
{
  EFI_STATUS Status;
  UINTN Done = 0;
  if ((File == NULL) || (Destination == NULL) || (Bytes == 0)) { return EFI_INVALID_PARAMETER; }
  Status = File->SetPosition (File, 0);
  if (EFI_ERROR (Status)) { return Status; }
  while (Done < Bytes) {
    UINTN Chunk = MIN (Bytes - Done, SIZE_1MB);
    UINTN Actual = Chunk;
    Status = File->Read (File, &Actual, (UINT8 *)Destination + Done);
    if (EFI_ERROR (Status)) { return Status; }
    // A short read fails before ExitBootServices. Never boot a partial APFS.
    if (Actual != Chunk) { return EFI_DEVICE_ERROR; }
    Done += Actual;
  }
  return EFI_SUCCESS;
}
#endif
