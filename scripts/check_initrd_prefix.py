"""Exercise the exact A/B FAT selector compiled into the odin DXE driver."""
from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
out=DEV/'build/initrd-prefix-test';out.mkdir(parents=True,exist_ok=True)
src=DEV/'build/UniXNURamDiskDxe/UniXNURamDiskDxe-odin.c'
provider=src.parent
records=json.loads((provider/'vendor-prefix.json').read_text())['prefixes']
for r in records:
 b=(ROOT/('outputs/MIX4-boot-backup-20261026/vendor_boot_'+r['slot']+'.img')).read_bytes()
 prefix=b[r['vendor_ramdisk_offset']:][:r['vendor_ramdisk_bytes']]
 assert hashlib.sha256(prefix).hexdigest()==r['vendor_ramdisk_sha256']
 (out/('prefix-'+r['slot']+'.bin')).write_bytes(prefix)
assert 'OdinSelectInitrd(&Start,End,' in src.read_text()
harness=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef uint8_t UINT8; typedef uint32_t UINT32; typedef uint64_t UINT64;
typedef uintptr_t UINTN; typedef void VOID; typedef int BOOLEAN; typedef int EFI_STATUS;
#define STATIC static
#define CONST const
#define TRUE 1
#define FALSE 0
#define EFI_SUCCESS 0
#define EFI_COMPROMISED_DATA 33
#define EFI_NOT_FOUND 14
#define EFI_ERROR(x) ((x)!=0)
static int crc32stub(VOID *p,UINTN n,UINT32 *result){UINT32 c=~0u;UINT8 *b=p;for(UINTN i=0;i<n;i++){c^=b[i];for(int k=0;k<8;k++)c=(c>>1)^(0xedb88320u&-(c&1));}*result=~c;return 0;}
static struct {int (*CalculateCrc32)(VOID*,UINTN,UINT32*);} services={crc32stub},*gBS=&services;
#include "OdinSelectInitrd.h"
static unsigned cases;
static void check(UINT8 *data,UINTN n,int ok,UINTN skip,UINTN expected){
 UINT64 start=(UINTN)data,bytes=0,skipped=0;
 EFI_STATUS status=OdinSelectInitrd(&start,(UINTN)data+n,&bytes,&skipped);
 assert((status==EFI_SUCCESS)==ok);
 if(ok){assert(start==(UINTN)data+skip);assert(skipped==skip);assert(bytes==expected);}
 else assert(start==(UINTN)data);
 cases++;
}
int main(int argc,char **argv){
 assert(argc==4);FILE *f=fopen(argv[3],"rb");assert(f);fseek(f,0,SEEK_END);size_t nf=(size_t)ftell(f);rewind(f);
 UINT8 *fat=malloc(nf+512);assert(fat);assert(fread(fat,1,nf,f)==nf);fclose(f);memset(fat+nf,0,512);
 check(fat,nf,1,0,nf);check(fat,nf+512,1,0,nf);check(fat,nf-1,0,0,0);
 check(fat,511,0,0,0);fat[511]^=1;check(fat,nf,0,0,0);fat[511]^=1;
 for(unsigned i=0;i<2;i++){
  f=fopen(argv[i+1],"rb");assert(f);size_t n=(size_t)mOdinPrefixes[i].Bytes,pad=(size_t)mOdinPrefixes[i].PaddedBytes;
  UINT8 *p=calloc(1,pad+nf+512);assert(p);assert(fread(p,1,n,f)==n);fclose(f);
  memcpy(p+n,fat,nf);check(p,n+nf,1,n,nf);
  p[100]^=1;check(p,n+nf,0,0,0);p[100]^=1;
  check(p,n+nf-1,0,0,0);
  memset(p+n,0,pad-n);memcpy(p+pad,fat,nf);
  check(p,pad+nf,1,pad,nf);check(p,pad+nf+512,1,pad,nf);
  check(p,n+511,0,0,0);free(p);
 }
 free(fat);assert(cases==17);printf("%u real FAT / A+B prefix cases passed\n",cases);return 0;
}
'''
(out/'test.c').write_text(harness)
cc=shutil.which('gcc');assert cc
cmd=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(provider),str(out/'test.c'),'-o',str(out/'test.exe')]
p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
p=subprocess.run([str(out/'test.exe'),str(out/'prefix-a.bin'),str(out/'prefix-b.bin'),str(DEV/'build/prelinked-payload/payload.fat')],capture_output=True,text=True)
assert p.returncode==0,p.stdout+p.stderr
(out/'verification.json').write_text(json.dumps({'passed':True,'cases':17,'driver_source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'selector_sha256':hashlib.sha256((provider/'OdinSelectInitrd.h').read_bytes()).hexdigest(),'scope':'Exact compiled selector, real A/B backups and real 64 MiB FAT; mocked CRC UEFI service; no hardware qualification','command':cmd},indent=2)+'\n')
print(p.stdout.strip())
