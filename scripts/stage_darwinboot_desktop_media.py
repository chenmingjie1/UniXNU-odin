"""Apply the odin desktop media handoff to an isolated DarwinBoot staging tree.

The pinned upstream component is never edited. The caller still obtains its
whole kernel window from real UEFI conventional memory; no guessed PA is used.
"""
from pathlib import Path


def stage_desktop_media(staged: Path):
    path = staged / 'PackedRamdisk.h'
    source = path.read_text()
    old = 'if ((InputSize > SIZE_256MB) || ((Input == NULL) != (InputSize == 0)))'
    assert source.count(old) == 1
    # The original 256 MiB cap rejects the actual 2.48 GB System fixture.
    # Packed inputs keep the upstream cap; only raw page-aligned disks gain room.
    source = source.replace(old, 'if ((InputSize > 0xc0000000ULL) || ((Input == NULL) != (InputSize == 0)))')
    source = source.replace(
        'if ((InputSize < 8) || (CompareMem (Input, "DBRDISK1", 8) != 0)) { return TRUE; }',
        'if ((InputSize < 8) || (CompareMem (Input, "DBRDISK1", 8) != 0)) { return (InputSize & (EFI_PAGE_SIZE - 1)) == 0; }\n'
        '  if (InputSize > SIZE_256MB) { return FALSE; }')
    path.write_text(source)

    path = staged / 'DarwinBoot.c'
    source = path.read_text()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, (old[:100], source.count(old))
        source = source.replace(old, new)

    # Extend the existing strict ADT parser; reject misplaced or duplicate media.
    source = source.replace('UINTN *RamdiskOffset, UINTN *TrustCacheOffset',
                            'UINTN *RamdiskOffset, UINTN *DataOffset, UINTN *TrustCacheOffset')
    source = source.replace('RamdiskOffset, TrustCacheOffset, AddonOffset',
                            'RamdiskOffset, DataOffset, TrustCacheOffset, AddonOffset')
    replace('  UINTN  TrustCandidate;', '  UINTN  DataCandidate;\n  UINTN  TrustCandidate;')
    replace('  TrustCandidate = MAX_UINTN;', '  DataCandidate = MAX_UINTN;\n  TrustCandidate = MAX_UINTN;')
    replace('    if (AsciiStrCmp ((CONST CHAR8 *)(Data + *Offset - 36), "TrustCache") == 0) {',
            '    if (AsciiStrCmp ((CONST CHAR8 *)(Data + *Offset - 36), "OdinDataRAMDisk") == 0) {\n'
            '      if ((DataCandidate != MAX_UINTN) || (Length != 16)) { return FALSE; }\n'
            '      DataCandidate = *Offset;\n'
            '    }\n'
            '    if (AsciiStrCmp ((CONST CHAR8 *)(Data + *Offset - 36), "TrustCache") == 0) {')
    replace('  if ((Path == 2) && (TrustCandidate != MAX_UINTN)) {',
            '  if (DataCandidate != MAX_UINTN) {\n'
            '    if ((Path != 2) || (*DataOffset != MAX_UINTN)) { return FALSE; }\n'
            '    *DataOffset = DataCandidate;\n'
            '  }\n'
            '  if ((Path == 2) && (TrustCandidate != MAX_UINTN)) {')
    replace('  UINTN                           RamdiskOffset;',
            '  VOID                            *DataSeed;\n'
            '  UINTN                           DataSize;\n'
            '  UINTN                           DataOffset;\n'
            '  UINT64                          DataAddress;\n'
            '  UINTN                           RamdiskOffset;')
    replace('  Root = NULL;', '  DataSeed = NULL;\n  DataSize = 0;\n  Root = NULL;')
    replace('  RamdiskOffset = MAX_UINTN;', '  RamdiskOffset = MAX_UINTN;\n  DataOffset = MAX_UINTN;')
    replace('&RamdiskOffset, &TrustCacheOffset, &AddonOffset',
            '&RamdiskOffset, &DataOffset, &TrustCacheOffset, &AddonOffset')
    replace('  CopyMem (TreePath, Request->KernelPath, Length);\n  StrCatS (TreePath, Length / sizeof (CHAR16) + 11, L".trustcache");',
            '  // Optional, private volatile Data seed; never a phone partition.\n'
            '  CopyMem (TreePath, Request->KernelPath, Length);\n'
            '  StrCatS (TreePath, Length / sizeof (CHAR16) + 11, L".data");\n'
            '  Status = ReadFile (Root, TreePath, SIZE_512MB, &DataSeed, &DataSize);\n'
            '  if (EFI_ERROR (Status) && (Status != EFI_NOT_FOUND)) { goto Fail; }\n'
            '  if (DataSeed != NULL) {\n'
            '    if ((DataOffset == MAX_UINTN) || (DataSize == 0) || (DataSize & (EFI_PAGE_SIZE - 1)) ||\n'
            '        (U64 ((UINT8 *)Tree + DataOffset) != 0) || (U64 ((UINT8 *)Tree + DataOffset + 8) != 0)) {\n'
            '      Status = EFI_COMPROMISED_DATA; goto Fail;\n'
            '    }\n'
            '  } else if (DataOffset != MAX_UINTN) { Status = EFI_COMPROMISED_DATA; goto Fail; }\n'
            '  CopyMem (TreePath, Request->KernelPath, Length);\n'
            '  StrCatS (TreePath, Length / sizeof (CHAR16) + 11, L".trustcache");')
    replace('  TrustCacheAddress = RamdiskAddress + RamdiskBytes;',
            '  DataAddress = RamdiskAddress + RamdiskBytes;\n'
            '  TrustCacheAddress = DataAddress + DataSize;')
    replace('  if (TrustCaches != NULL) {\n    CopyMem ((VOID *)(UINTN)TrustCacheAddress, TrustCaches, TrustCacheSize);',
            '  if (DataSeed != NULL) {\n'
            '    CopyMem ((VOID *)(UINTN)DataAddress, DataSeed, DataSize);\n'
            '    WriteUnaligned64 ((UINT64 *)(UINTN)(TreeAddress + DataOffset), DataAddress);\n'
            '    WriteUnaligned64 ((UINT64 *)(UINTN)(TreeAddress + DataOffset + 8), DataSize);\n'
            '    FreePool (DataSeed); DataSeed = NULL;\n'
            '  }\n'
            '  if (TrustCaches != NULL) {\n    CopyMem ((VOID *)(UINTN)TrustCacheAddress, TrustCaches, TrustCacheSize);')
    replace('  if (Image != NULL) { FreePool (Image); }',
            '  if (DataSeed != NULL) { FreePool (DataSeed); }\n'
            '  if (Image != NULL) { FreePool (Image); }')
    # Read the large raw sidecars directly into the reserved window. Holding a
    # second 2.48 GB System buffer can fragment the phone's conventional RAM
    # before the required contiguous 4 GiB window is allocated.
    replace('#include "PackedRamdisk.h"', '#include "PackedRamdisk.h"\n#include "OdinDesktopMedia.h"')
    replace('  VOID                            *DataSeed;',
            '  EFI_FILE_PROTOCOL               *SystemFile;\n'
            '  EFI_FILE_PROTOCOL               *DataFile;')
    replace('  DataSeed = NULL;', '  SystemFile = NULL;\n  DataFile = NULL;')
    replace('  if (Request->Ramdisk != NULL) {\n    if ((RamdiskOffset == MAX_UINTN)',
            '  CopyMem (TreePath, Request->KernelPath, Length);\n'
            '  StrCatS (TreePath, Length / sizeof (CHAR16) + 11, L".system");\n'
            '  Status = OdinOpenMedia (Root, TreePath, 0xc0000000ULL, &SystemFile, &RamdiskBytes);\n'
            '  if (EFI_ERROR (Status) && (Status != EFI_NOT_FOUND)) { goto Fail; }\n'
            '  if (SystemFile != NULL) {\n'
            '    if ((Request->Ramdisk != NULL) || KeepPacked) { Status = EFI_COMPROMISED_DATA; goto Fail; }\n'
            '    RamdiskExpandedSize = RamdiskBytes;\n'
            '  }\n'
            '  if ((Request->Ramdisk != NULL) || (SystemFile != NULL)) {\n    if ((RamdiskOffset == MAX_UINTN)')
    replace('  Status = ReadFile (Root, TreePath, SIZE_512MB, &DataSeed, &DataSize);',
            '  Status = OdinOpenMedia (Root, TreePath, SIZE_512MB, &DataFile, &DataSize);')
    source = source.replace('DataSeed != NULL', 'DataFile != NULL')
    replace('  if (Request->Ramdisk != NULL) {\n    if (KeepPacked)',
            '  if ((Request->Ramdisk != NULL) || (SystemFile != NULL)) {\n'
            '    if (SystemFile != NULL) {\n'
            '      Status = OdinReadMedia (SystemFile, (VOID *)(UINTN)RamdiskAddress, RamdiskBytes);\n'
            '      if (EFI_ERROR (Status)) { goto Fail; }\n'
            '      SystemFile->Close (SystemFile); SystemFile = NULL;\n'
            '    } else if (KeepPacked)')
    replace('    CopyMem ((VOID *)(UINTN)DataAddress, DataSeed, DataSize);',
            '    Status = OdinReadMedia (DataFile, (VOID *)(UINTN)DataAddress, DataSize);\n'
            '    if (EFI_ERROR (Status)) { goto Fail; }')
    replace('    FreePool (DataSeed); DataSeed = NULL;',
            '    DataFile->Close (DataFile); DataFile = NULL;')
    replace('  if (DataFile != NULL) { FreePool (DataSeed); }',
            '  if (SystemFile != NULL) { SystemFile->Close (SystemFile); }\n'
            '  if (DataFile != NULL) { DataFile->Close (DataFile); }')
    (staged / 'OdinDesktopMedia.h').write_bytes(
        (Path(__file__).resolve().parents[1] / 'firmware/OdinDesktopMedia.h').read_bytes())
    path.write_text(source)
