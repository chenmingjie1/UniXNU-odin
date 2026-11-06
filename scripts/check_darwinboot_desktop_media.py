"""Execute the staged C ADT/ramdisk parsers with real and malformed inputs."""
from pathlib import Path
import copy
import hashlib
import json
import re
import struct
import subprocess
from adt_codec import decode, encode, lookup

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = DEV / 'build/darwinboot-u63/check'
STAGED = OUT.parent / 'source'
OUT.mkdir(exist_ok=True)
source = (STAGED / 'DarwinBoot.c').read_text()
parser = re.search(r'STATIC\s+BOOLEAN\s+AdtNode \(.*?\n}\n', source, re.S)[0]
tree = decode((DEV / 'build/prelinked-payload-u08/esp/EFI/UniXNU/Payloads/kernel.macho.adt').read_bytes())
lookup(tree, 'chosen', 'memory-map')['OdinDataRAMDisk'] = bytes(16)
cases = [('valid', tree, True)]
bad = copy.deepcopy(tree)
lookup(bad, 'chosen', 'memory-map')['OdinDataRAMDisk'] = bytes(8)
cases.append(('short-data-range', bad, False))
bad = copy.deepcopy(tree)
bad[0]['OdinDataRAMDisk'] = bytes(16)
cases.append(('misplaced-data-range', bad, False))
bad = copy.deepcopy(tree)
lookup(bad, 'chosen')['darwinboot-memory-size'] = struct.pack('<Q', 0x100000001)
cases.append(('unaligned-window', bad, False))
bad = copy.deepcopy(tree)
lookup(bad, 'chosen')['darwinboot-memory-size'] = struct.pack('<Q', 0x300000000)
cases.append(('oversized-window', bad, False))
prefix = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint8_t UINT8; typedef uint32_t UINT32; typedef uint64_t UINT64;
typedef size_t UINTN; typedef int BOOLEAN; typedef char CHAR8; typedef void VOID;
#define STATIC static
#define CONST const
#define TRUE 1
#define FALSE 0
#define MAX_UINTN SIZE_MAX
#define EFI_PAGE_SIZE 4096
#define SIZE_256MB 0x10000000ULL
#define ALIGN_VALUE(n,a) (((n)+(a)-1)&~((a)-1))
#define CompareMem memcmp
#define CopyMem memcpy
#define AsciiStrCmp strcmp
#define ScanMem8(p,n,v) memchr(p,v,n)
static UINT32 U32(const void *p){UINT32 n;memcpy(&n,p,4);return n;}
static UINT64 U64(const void *p){UINT64 n;memcpy(&n,p,8);return n;}
#define ReadUnaligned32 U32
#define ReadUnaligned64 U64
#include "WindowSize.h"
#include "PackedRamdisk.h"
typedef uint16_t CHAR16; typedef int EFI_STATUS;
#define EFI_SUCCESS 0
#define EFI_NOT_FOUND 1
#define EFI_BUFFER_TOO_SMALL 2
#define EFI_DEVICE_ERROR 3
#define EFI_BAD_BUFFER_SIZE 4
#define EFI_OUT_OF_RESOURCES 5
#define EFI_INVALID_PARAMETER 6
#define EFI_ERROR(s) ((s)!=0)
#define EFI_FILE_MODE_READ 1
#define EFI_FILE_DIRECTORY 16
#define SIZE_1MB 1048576
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef struct {UINT64 FileSize, Attribute;} EFI_FILE_INFO;
#define SIZE_OF_EFI_FILE_INFO sizeof(EFI_FILE_INFO)
static int gEfiFileInfoGuid;
static void *AllocatePool(UINTN n){assert(n<=65536);return malloc(n);}
#define FreePool free
typedef struct EFI_FILE_PROTOCOL EFI_FILE_PROTOCOL;
struct EFI_FILE_PROTOCOL {
  EFI_STATUS (*Open)(EFI_FILE_PROTOCOL *,EFI_FILE_PROTOCOL **,CHAR16 *,UINT64,UINT64);
  EFI_STATUS (*GetInfo)(EFI_FILE_PROTOCOL *,void *,UINTN *,void *);
  EFI_STATUS (*Close)(EFI_FILE_PROTOCOL *);
  EFI_STATUS (*Read)(EFI_FILE_PROTOCOL *,UINTN *,void *);
  EFI_STATUS (*SetPosition)(EFI_FILE_PROTOCOL *,UINT64);
};
#include "OdinDesktopMedia.h"
static EFI_FILE_PROTOCOL mock;
static UINT64 mockSize=2478948352ULL,mockPosition;
static UINTN mockReads,mockCloses;
static int mockShort,mockReadError,mockSeekError,mockDirectory;
static EFI_STATUS mockOpen(EFI_FILE_PROTOCOL *r,EFI_FILE_PROTOCOL **f,CHAR16 *p,UINT64 m,UINT64 a){(void)r;(void)p;(void)a;assert(m==1);*f=&mock;return 0;}
static EFI_STATUS mockInfo(EFI_FILE_PROTOCOL *f,void *g,UINTN *n,void *b){(void)f;(void)g;if(!b){*n=sizeof(EFI_FILE_INFO);return EFI_BUFFER_TOO_SMALL;}EFI_FILE_INFO *i=b;i->FileSize=mockSize;i->Attribute=mockDirectory?16:0;return 0;}
static EFI_STATUS mockClose(EFI_FILE_PROTOCOL *f){(void)f;mockCloses++;return 0;}
static EFI_STATUS mockSeek(EFI_FILE_PROTOCOL *f,UINT64 p){(void)f;mockPosition=p;return mockSeekError?EFI_DEVICE_ERROR:0;}
static EFI_STATUS mockRead(EFI_FILE_PROTOCOL *f,UINTN *n,void *b){(void)f;assert(*n<=SIZE_1MB);mockReads++;if(mockReadError)return EFI_DEVICE_ERROR;if(mockShort)(*n)--;memset(b,0x5a,*n);mockPosition+=*n;return 0;}
'''
body = r'''
int main(void) {
  UINTN expanded, offset, ram, data, trust, addon, policy; UINT64 window;
  BOOLEAN packed, keep; unsigned char raw[8]={0};
  assert(RamdiskLayout(NULL,0,&expanded,&packed));
  assert(!RamdiskLayout(NULL,4096,&expanded,&packed));
  assert(!RamdiskLayout(raw,0,&expanded,&packed));
  assert(RamdiskLayout(raw,2478948352ULL,&expanded,&packed));
  assert(expanded==2478948352ULL && !packed);
  assert(RamdiskLayout(raw,0xc0000000ULL,&expanded,&packed));
  assert(!RamdiskLayout(raw,0xc0001000ULL,&expanded,&packed));
  assert(!RamdiskLayout(raw,4095,&expanded,&packed));
  unsigned char header[32]={'D','B','R','D','I','S','K','1',1,0,0,0,0,16,0,0};
  UINT64 logical=4096;memcpy(header+16,&logical,8);
  assert(RamdiskLayout(header,32,&expanded,&packed) && packed && expanded==4096);
  assert(!RamdiskLayout(header,0x10000001ULL,&expanded,&packed));
  assert(!RamdiskLayout(header,31,&expanded,&packed));
  mock=(EFI_FILE_PROTOCOL){mockOpen,mockInfo,mockClose,mockRead,mockSeek};
  EFI_FILE_PROTOCOL *opened;UINTN mediaBytes;CHAR16 name[1]={0};
  assert(!OdinOpenMedia(&mock,name,0xc0000000ULL,&opened,&mediaBytes));
  assert(opened==&mock && mediaBytes==2478948352ULL);
  assert(OdinOpenMedia(&mock,name,0x10000000ULL,&opened,&mediaBytes)==EFI_BAD_BUFFER_SIZE);
  assert(!opened && !mediaBytes && mockCloses==1);
  mockDirectory=1;assert(OdinOpenMedia(&mock,name,0xc0000000ULL,&opened,&mediaBytes)==EFI_BAD_BUFFER_SIZE);mockDirectory=0;
  mockSize=4095;assert(OdinOpenMedia(&mock,name,0xc0000000ULL,&opened,&mediaBytes)==EFI_BAD_BUFFER_SIZE);mockSize=0;
  assert(OdinOpenMedia(&mock,name,0xc0000000ULL,&opened,&mediaBytes)==EFI_BAD_BUFFER_SIZE);
  UINTN actualSize=2*SIZE_1MB+4096;UINT8 *destination=malloc(actualSize);assert(destination);
  assert(!OdinReadMedia(&mock,destination,actualSize));
  assert(mockReads==3 && mockPosition==actualSize);
  for(UINTN j=0;j<actualSize;j++)assert(destination[j]==0x5a);
  mockShort=1;assert(OdinReadMedia(&mock,destination,actualSize)==EFI_DEVICE_ERROR);mockShort=0;
  mockReadError=1;assert(OdinReadMedia(&mock,destination,actualSize)==EFI_DEVICE_ERROR);mockReadError=0;
  mockSeekError=1;assert(OdinReadMedia(&mock,destination,actualSize)==EFI_DEVICE_ERROR);mockSeekError=0;
  assert(OdinReadMedia(NULL,destination,actualSize)==EFI_INVALID_PARAMETER);
  free(destination);
'''
checks = []
for name, item, valid in cases:
    binary = encode(item)
    (OUT / (name + '.adt')).write_bytes(binary)
    variable = name.replace('-', '_')
    body += '{\nunsigned char ' + variable + '[]={' + ','.join(map(str, binary)) + '};\n'
    body += 'offset=0;ram=data=trust=addon=policy=MAX_UINTN;window=0;keep=FALSE;\n'
    call = f'AdtNode({variable},sizeof({variable}),&offset,0,3,&ram,&data,&trust,&addon,&policy,&window,&keep)'
    body += f'assert({call} == {int(valid)});\n'
    if valid:
        body += f'assert(offset==sizeof({variable}) && data!=MAX_UINTN);\n'
        # Exercise every truncation through the production parser, not the Python codec.
        body += f'for(UINTN n=0;n<sizeof({variable});n++){{offset=0;ram=data=trust=addon=policy=MAX_UINTN;window=0;keep=FALSE;assert(!AdtNode({variable},n,&offset,0,3,&ram,&data,&trust,&addon,&policy,&window,&keep));}}\n'
        checks.append({'case': 'all-adt-truncations', 'count': len(binary)})
    body += '}\n'
    checks.append({'case': name, 'expected_accept': valid})
body += 'puts("Production ADT and ramdisk parser checks passed");return 0;}\n'
(OUT / 'parsers.c').write_text(prefix + parser + body)
compiler = ROOT / 'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin/clang.exe'
cmd = [str(compiler), '-O1', '-Wall', '-Wextra', '-I', str(STAGED), str(OUT / 'parsers.c'), '-o', str(OUT / 'parsers.exe')]
result = subprocess.run(cmd, capture_output=True, text=True)
(OUT / 'compile.log').write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
result = subprocess.run([str(OUT / 'parsers.exe')], capture_output=True, text=True)
assert result.returncode == 0, result.stdout + result.stderr
report = {'passed': True, 'device_commands': False, 'scope': 'Native host execution of actual staged production parsers; not hardware qualification',
          'source_sha256': hashlib.sha256((STAGED / 'DarwinBoot.c').read_bytes()).hexdigest(), 'checks': checks,
          'raw_root_bytes_accepted': 2478948352, 'raw_limit_bytes': 0xc0000000,
          'packed_input_limit_bytes': 0x10000000,
          'streaming_checks': ['2.48GB file metadata without full pool allocation', 'multi-chunk byte-for-byte copy',
                               'short read rejected', 'read failure rejected', 'seek failure rejected',
                               'directory rejected', 'zero/unaligned/oversized files rejected'],
          'result': result.stdout.strip(), 'compiler': cmd}
(OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
