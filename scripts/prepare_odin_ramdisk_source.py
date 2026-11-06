"""Apply bounded odin A/B initrd recognition and readable driver telemetry."""
from pathlib import Path
import hashlib, json, struct, zlib

def prepare(root, source, out):
    records=[]
    for slot in 'ab':
        vendor=root/f'outputs/MIX4-boot-backup-20261026/vendor_boot_{slot}.img'
        b=vendor.read_bytes()
        assert b[:8]==b'VNDRBOOT' and struct.unpack_from('<I',b,8)[0]==3
        page=struct.unpack_from('<I',b,12)[0];size=struct.unpack_from('<I',b,24)[0]
        offset=(struct.unpack_from('<I',b,2096)[0]+page-1)//page*page
        prefix=b[offset:offset+size];assert len(prefix)==size
        records.append(dict(slot=slot,vendor_boot_sha256=hashlib.sha256(b).hexdigest(),
          vendor_ramdisk_offset=offset,vendor_ramdisk_bytes=size,padded_bytes=(size+page-1)//page*page,
          vendor_ramdisk_sha256=hashlib.sha256(prefix).hexdigest(),runtime_prefix_crc32=zlib.crc32(prefix)&0xffffffff))
    (out/'OdinVendorPrefixes.h').write_text('STATIC CONST struct {UINT64 Bytes; UINT64 PaddedBytes; UINT32 Crc;} mOdinPrefixes[] = {\n'+''.join(
      ' {%dULL,%dULL,0x%08xU},\n'%(r['vendor_ramdisk_bytes'],r['padded_bytes'],r['runtime_prefix_crc32']) for r in records)+'};\n')
    helper=Path(__file__).with_name('OdinSelectInitrd.h')
    (out/helper.name).write_bytes(helper.read_bytes())
    text=source.read_text()
    def change(old,new):
        nonlocal text
        assert text.count(old)==1,old
        text=text.replace(old,new)
    change('#define RAM_BLOCK_SIZE  512', '''#define RAM_BLOCK_SIZE  512
#include "OdinSelectInitrd.h"
STATIC EFI_GUID mOdinRamDiagGuid={0x71b5b2d3,0xe375,0x446a,{0x93,0x18,0x0d,0x14,0x49,0x69,0xa5,0x05}};
// revision, stage, status, DTB, raw start/end, selected base/size, prefix skip
STATIC UINT64 mOdinRamDiag[9]={1,0,EFI_NOT_READY,0,0,0,0,0,0};''')
    change('  Chosen = FdtPathOffset', '  mOdinRamDiag[1]=4;\n  Chosen = FdtPathOffset')
    change('    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no /chosen\\n"));', '    mOdinRamDiag[2]=EFI_NOT_FOUND;\n    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no /chosen\\n"));')
    change('    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));', '    mOdinRamDiag[2]=EFI_NOT_FOUND;\n    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));')
    needle='  if ((End <= Start) || (((End - Start) % RAM_BLOCK_SIZE) != 0)) {'
    change(needle, '''  mOdinRamDiag[1]=5;mOdinRamDiag[4]=Start;mOdinRamDiag[5]=End;
  Status=OdinSelectInitrd(&Start,End,&mOdinRamDiag[7],&mOdinRamDiag[8]);
  mOdinRamDiag[2]=Status;
  if(EFI_ERROR(Status))return;
  End=Start+mOdinRamDiag[7];
  mOdinRamDiag[1]=6;mOdinRamDiag[6]=Start;
'''+needle)
    change('  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: initrd block device', '  mOdinRamDiag[1]=7;mOdinRamDiag[2]=Status;\n  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: initrd block device')
    change('  UINT64             Dtb;', '  UINT64             Dtb;\n  EFI_HANDLE DiagHandle=NULL;\n  gBS->InstallProtocolInterface(&DiagHandle,&mOdinRamDiagGuid,EFI_NATIVE_INTERFACE,mOdinRamDiag);\n  mOdinRamDiag[1]=1;')
    change('    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));', '    mOdinRamDiag[2]=EFI_NOT_FOUND;\n    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));')
    change('  Dtb = ReadUnaligned64', '  mOdinRamDiag[1]=2;\n  Dtb = ReadUnaligned64')
    change('  if ((Dtb == 0)', '  mOdinRamDiag[3]=Dtb;\n  if ((Dtb == 0)')
    change('    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0', '    mOdinRamDiag[2]=EFI_COMPROMISED_DATA;\n    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0')
    change('  PublishInitrd ((VOID *)(UINTN)Dtb);', '  mOdinRamDiag[1]=3;\n  PublishInitrd ((VOID *)(UINTN)Dtb);')
    target=out/'UniXNURamDiskDxe-odin.c';target.write_text(text)
    (out/'vendor-prefix.json').write_text(json.dumps({'prefixes':records,
      'upstream_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'selector_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),
      'scope':'Direct FAT or exact A/B vendor prefix, tight or page-aligned; runtime pending'},indent=2)+'\n')
    return target
