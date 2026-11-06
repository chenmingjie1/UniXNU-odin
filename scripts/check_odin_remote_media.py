"""Execute real remote-filesystem callbacks and wire validation on the host."""
from pathlib import Path
import hashlib,json,subprocess
import argparse
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag',default='u64');parser.add_argument('--resident-core7',action='store_true');options=parser.parse_args()
assert options.tag.isalnum()
OUT=DEV/('build/remote-media-'+options.tag+'/check');OUT.mkdir(exist_ok=True)
source=r'''
#define ODIN_REMOTE_HOST_TEST
#include "OdinRemoteMedia.c"
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <stdarg.h>
EFI_BOOT_SERVICES services;
EFI_BOOT_SERVICES *gBS=&services;
EFI_RUNTIME_SERVICES *gRT;
VOID *EFIAPI AllocatePool(UINTN n){return malloc(n);}
VOID *EFIAPI AllocateZeroPool(UINTN n){return calloc(1,n);}
VOID EFIAPI FreePool(VOID *p){free(p);}
VOID *EFIAPI CopyMem(VOID *d,CONST VOID *s,UINTN n){return memmove(d,s,n);}
VOID *EFIAPI ZeroMem(VOID *p,UINTN n){return memset(p,0,n);}
INTN EFIAPI CompareMem(CONST VOID *a,CONST VOID *b,UINTN n){return memcmp(a,b,n);}
BOOLEAN EFIAPI CompareGuid(CONST GUID *a,CONST GUID *b){return !memcmp(a,b,16);}
UINTN EFIAPI StrLen(CONST CHAR16 *s){UINTN n=0;while(s[n])n++;return n;}
UINTN EFIAPI StrSize(CONST CHAR16 *s){return (StrLen(s)+1)*2;}
INTN EFIAPI StrCmp(CONST CHAR16 *a,CONST CHAR16 *b){while(*a && *a==*b){a++;b++;}return (INTN)*a-*b;}
UINT32 EFIAPI ReadUnaligned32(CONST VOID *p){UINT32 n;memcpy(&n,p,4);return n;}
UINT64 EFIAPI ReadUnaligned64(CONST VOID *p){UINT64 n;memcpy(&n,p,8);return n;}
EFI_GUID gEfiFileInfoGuid=EFI_FILE_INFO_ID;
EFI_GUID gEfiDevicePathProtocolGuid=EFI_DEVICE_PATH_PROTOCOL_GUID;
EFI_GUID gEfiSimpleFileSystemProtocolGuid=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
UINTN EFIAPI Print(CONST CHAR16 *Text,...){(VOID)Text;return 0;}
INTN EFIAPI AsciiStrCmp(CONST CHAR8 *a,CONST CHAR8 *b){return strcmp(a,b);}
UINTN EFIAPI AsciiSPrint(CHAR8 *Buffer,UINTN Size,CONST CHAR8 *Format,...){
 va_list args;va_start(args,Format);int n;
 if(!strcmp(Format,"core7:entered=%lx:fault=%lx")){UINT64 a=va_arg(args,UINT64),b=va_arg(args,UINT64);n=snprintf(Buffer,Size,"core7:entered=%llx:fault=%llx",(unsigned long long)a,(unsigned long long)b);}
 else {const char *a=va_arg(args,const char*);
  if(!strcmp(Format,"%a%a")){const char *b=va_arg(args,const char*);n=snprintf(Buffer,Size,"%s%s",a,b);}
  else {assert(!strcmp(Format,"%a:%016lx"));UINT64 b=va_arg(args,UINT64);n=snprintf(Buffer,Size,"%s:%016llx",a,(unsigned long long)b);}}
 va_end(args);assert(n>=0 && (UINTN)n<Size);return (UINTN)n;
}
static EFI_STATUS EFIAPI Crc(VOID *p,UINTN n,UINT32 *out){
 UINT32 c=0xffffffff;UINT8 *b=p;for(UINTN i=0;i<n;i++){c^=b[i];for(int j=0;j<8;j++)c=(c>>1)^((0-(c&1))&0xedb88320);}
 *out=~c;return EFI_SUCCESS;
}
static UINTN calls;static int failAt;
STATIC EFI_STATUS HostReadChunk(VOID *d){
 assert(mWanted>0 && mWanted<=SIZE_1MB);calls++;
 if(failAt && calls==(UINTN)failAt)return EFI_DEVICE_ERROR;
 for(UINTN i=0;i<mWanted;i++)((UINT8*)d)[i]=(UINT8)((mOffset+i)%251);
 return EFI_SUCCESS;
}
static UINTN pumps,sends,aborts,commandIndex;static int fault;static UINT8 pending;
static const char *commands[]={"getvar:product","getvar:odin-read","oem desktop"};
static BOOLEAN stopAfterCommands;
static EFI_STATUS EFIAPI MockStall(UINTN us){(VOID)us;return EFI_SUCCESS;}
static EFI_STATUS MockSend(UINT8 ep,UINTN n,VOID *buffer){
 assert(mConnected);sends++;if(fault==1)return EFI_DEVICE_ERROR;
 if(ep==OUT_EP && commandIndex==3 && stopAfterCommands){mSealed=TRUE;return EFI_DEVICE_ERROR;}
 if(ep==IN_EP){assert(n>=4);
  const char *command=commands[commandIndex-1];
#ifdef ODIN_RESIDENT_CORE7
  if(mResidentContext){
   if(!strcmp(command,"oem desktop"))assert(!memcmp(buffer,"FAIL",4));
   else assert(!memcmp(buffer,"OKAY",4));
   if(!strcmp(command,"getvar:odin-read"))assert(!strcmp((char*)buffer+4,"idle:kernel-core7"));
   if(!strcmp(command,"getvar:result"))assert(!strcmp((char*)buffer+4,"core7:entered=1:fault=0"));
  } else {
#endif
  if(!strcmp(command,"oem desktop") && mRecovering)assert(!memcmp(buffer,"FAIL",4));
  else assert(!memcmp(buffer,"OKAY",4));
  if(!strcmp(command,"getvar:product"))assert(!strcmp((char*)buffer+4,"odin-unixnu-u64"));
  if(!strcmp(command,"getvar:odin-read"))assert(!strcmp((char*)buffer+4,mRecovering?"idle:uefi-stopped":"idle:desktop-ready"));
  if(!strcmp(command,"getvar:result"))assert(!strcmp((char*)buffer+4,"darwin-return:8000000000000001"));
#ifdef ODIN_RESIDENT_CORE7
  }
#endif
 }
 pending=ep;return EFI_SUCCESS;
}
static EFI_STATUS MockAbort(UINT8 ep){(VOID)ep;aborts++;return EFI_SUCCESS;}
static EFI_STATUS MockEvent(USB_DEVICE_EVENT *event,UINTN *size,USB_DEVICE_EVENT_DATA *data){
 assert(*size==sizeof(*data));pumps++;*event=UsbDeviceEventNoEvent;
 if(fault==2)return EFI_DEVICE_ERROR;
 if(fault==3)return EFI_SUCCESS;
 if(!mConnected){if(pumps<4)return EFI_SUCCESS;*event=UsbDeviceEventDeviceStateChange;data->DeviceState=UsbDeviceStateConnected;return EFI_SUCCESS;}
 if(fault==4){*event=UsbDeviceEventDeviceStateChange;data->DeviceState=UsbDeviceStateDisconnected;return EFI_SUCCESS;}
 if(pending){*event=UsbDeviceEventTransferNotification;data->TransferOutcome.EndpointIndex=pending;
  data->TransferOutcome.Status=UsbDeviceTransferStatusCompleteOK;
  if(pending==OUT_EP){assert(commandIndex<3);UINTN n=strlen(commands[commandIndex]);memcpy(mRx,commands[commandIndex++],n);data->TransferOutcome.BytesCompleted=n;}
  else data->TransferOutcome.BytesCompleted=strlen((char*)mTx);
  pending=0;
 }
 return EFI_SUCCESS;
}
static UNIXNU_LOADER_PROTOCOL testLoader;static EFI_STATUS locateResult;static UINTN bootCalls;
static EFI_STATUS EFIAPI MockLocate(EFI_GUID *guid,VOID *registration,VOID **out){
 EFI_GUID expected=UNIXNU_LOADER_PROTOCOL_GUID;(VOID)registration;assert(CompareGuid(guid,&expected));
 if(EFI_ERROR(locateResult))return locateResult;*out=&testLoader;return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI MockBoot(UNIXNU_LOADER_PROTOCOL *self,CONST UNIXNU_LOADER_BOOT_REQUEST *request){
 assert(self==&testLoader && request->KernelPath && !StrCmp(request->KernelPath,L"kernel.macho"));bootCalls++;return EFI_LOAD_ERROR;
}
static void CheckHandshake(void){
 static EFI_USB_DEVICE_PROTOCOL usb;static UINT8 rx[64],tx[64];
 usb.Send=MockSend;usb.HandleEvent=MockEvent;usb.AbortXfer=MockAbort;
 mUsb=&usb;mRx=rx;mTx=tx;mStarted=TRUE;services.Stall=MockStall;
 assert(!OdinRemoteHandshake());assert(commandIndex==3 && sends==6 && pumps>=10);
 fault=1;assert(Transfer(OUT_EP,64)==-1);
 fault=2;mConnected=FALSE;UINTN before=sends;assert(Transfer(OUT_EP,64)==-1 && sends==before);
 fault=3;mHostCounterStep=19200000;before=sends;assert(Transfer(OUT_EP,64)==-1 && sends==before);
 fault=4;mConnected=TRUE;assert(Transfer(OUT_EP,64)==-1 && !mConnected && aborts==1);
 mSealed=TRUE;assert(OdinRemoteHandshake()==EFI_UNSUPPORTED);
 services.LocateProtocol=MockLocate;locateResult=EFI_NOT_FOUND;
 assert(OdinRemoteInstallLoaderGuard()==EFI_NOT_FOUND);
 locateResult=EFI_SUCCESS;assert(OdinRemoteInstallLoaderGuard()==EFI_UNSUPPORTED);
 testLoader.Revision=UNIXNU_LOADER_REVISION;testLoader.Boot=MockBoot;
 assert(!OdinRemoteInstallLoaderGuard() && testLoader.Boot==GuardedBoot && mOriginalBoot==MockBoot);
 assert(!OdinRemoteInstallLoaderGuard() && mOriginalBoot==MockBoot);
 UNIXNU_LOADER_BOOT_REQUEST request={0};request.KernelPath=L"kernel.macho";
 assert(testLoader.Boot(&testLoader,&request)==EFI_LOAD_ERROR && bootCalls==1);
 mSealed=FALSE;mConnected=TRUE;fault=0;pending=0;commandIndex=0;stopAfterCommands=TRUE;
 commands[0]="getvar:result";
 assert(testLoader.Boot(&testLoader,&request)==EFI_LOAD_ERROR && bootCalls==2);
 assert(mRecovering && mSealed && commandIndex==3);
#ifdef ODIN_RESIDENT_CORE7
 ODIN_RESIDENT_CONTEXT context={0};context.Entered=1;mResidentContext=&context;
 mSealed=FALSE;mRecovering=FALSE;commandIndex=0;pending=0;
 commands[0]="getvar:result";commands[1]="getvar:odin-read";commands[2]="oem desktop";
 assert(OdinRemoteHandshake()==EFI_TIMEOUT && commandIndex==3 && mSealed);
 mResidentContext=NULL;
#endif
}
int main(void){
 services.CalculateCrc32=Crc;EFI_FILE_PROTOCOL *root,*file,*directory;EFI_STATUS s;UINTN size;UINT64 position;
 assert(mFs.OpenVolume(&mFs,&root)==EFI_SUCCESS);
 assert(root->Open(root,&directory,L"\\EFI\\UniXNU",EFI_FILE_MODE_READ,0)==EFI_SUCCESS);
 assert(directory->Open(directory,&file,L"Payloads/kernel.macho.system",EFI_FILE_MODE_READ,0)==EFI_SUCCESS);
 assert(file->GetInfo(file,&gEfiFileInfoGuid,&(UINTN){0},NULL)==EFI_BUFFER_TOO_SMALL);
 size=1024;EFI_FILE_INFO *info=malloc(size);assert(!file->GetInfo(file,&gEfiFileInfoGuid,&size,info));
 assert(info->FileSize==2478948352ULL && !(info->Attribute&EFI_FILE_DIRECTORY));free(info);
 size=2*SIZE_1MB+4096;UINT8 *bytes=malloc(size);assert(bytes);
 assert(!file->Read(file,&size,bytes) && size==2*SIZE_1MB+4096 && calls==3);
 for(UINTN i=0;i<size;i++)assert(bytes[i]==i%251);
 assert(!file->GetPosition(file,&position) && position==size);
 assert(file->SetPosition(file,2478948353ULL)==EFI_INVALID_PARAMETER);
 assert(!file->SetPosition(file,MAX_UINT64));size=8192;assert(!file->Read(file,&size,bytes)&&!size);
 assert(!file->SetPosition(file,0));calls=0;failAt=2;size=2*SIZE_1MB;
 assert(file->Read(file,&size,bytes)==EFI_DEVICE_ERROR && size==SIZE_1MB);
 assert(!file->GetPosition(file,&position)&&position==SIZE_1MB);failAt=0;
 assert(file->Write(file,&size,bytes)==EFI_WRITE_PROTECTED);
 assert(file->Close(file)==EFI_SUCCESS);assert(!directory->Close(directory));
 assert(root->Open(root,&file,L"\\EFI\\UniXNU\\missing",EFI_FILE_MODE_READ,0)==EFI_NOT_FOUND);
 assert(root->Open(root,&file,L"\\EFI\\..\\x",EFI_FILE_MODE_READ,0)==EFI_NOT_FOUND);
 assert(root->Open(root,&file,L"\\EFI",EFI_FILE_MODE_CREATE|EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE,0)==EFI_WRITE_PROTECTED);
 assert(!root->Close(root));free(bytes);
 UINT8 response[4096+32]={0};memcpy(response,"ODNRD001",8);
 UINT32 seq=23,id=8,want=4096,crc;UINT64 off=0x1234000;
 memcpy(response+8,&seq,4);memcpy(response+12,&id,4);memcpy(response+16,&off,8);memcpy(response+24,&want,4);
 memset(response+32,0x5a,want);Crc(response+32,want,&crc);memcpy(response+28,&crc,4);
 assert(!OdinValidateResponse(response,sizeof(response),seq,id,off,want));
 for(UINTN n=0;n<sizeof(response);n++){response[n]^=1;s=OdinValidateResponse(response,sizeof(response),seq,id,off,want);assert(EFI_ERROR(s));response[n]^=1;}
 for(UINTN n=0;n<sizeof(response);n++)assert(EFI_ERROR(OdinValidateResponse(response,n,seq,id,off,want)));
 assert(EFI_ERROR(OdinValidateResponse(response,sizeof(response),seq,id,off,SIZE_1MB+1)));
 CheckHandshake();
 puts("Production filesystem, 8256 wire checks, USB handshake, and pre-EBS loader failure recovery simulation passed");return 0;
}
'''
configured=json.loads((OUT.parent/'verification.json').read_text())
system_file=next(item for item in configured['files'] if item['path'] and item['path'].endswith('.system'))
system_size=Path(system_file['path']).stat().st_size
assert system_size==system_file['bytes'] and system_size>2*1024**2
source=source.replace('2478948352ULL',str(system_size)+'ULL').replace('2478948353ULL',str(system_size+1)+'ULL')
(OUT/'check.c').write_text(source)
BIN=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
MU=ROOT/'work/Mu-Silicium-odin'
cmd=[str(BIN/'clang.exe'),'-O1','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
     *(['-DODIN_RESIDENT_CORE7=1'] if options.resident_core7 else []),
     '-fshort-wchar','-D_EFI_X64_','-I',str(OUT.parent),'-I',str(MU/'Mu_Basecore/MdePkg/Include'),
     '-I',str(MU/'Mu_Basecore/MdePkg/Include/X64'),'-I',str(MU/'Silicon/Qualcomm/QcomPkg/Include'),
     '-I',str(ROOT/'work/UniXNU-source/UniXNU-04573c510c5fd4892ca6948739389141cc9e05f5/package/UniXNUPkg/Include'),
     str(OUT/'check.c'),'-o',str(OUT/'check.exe')]
r=subprocess.run(cmd,capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr)
assert r.returncode==0,r.stdout+r.stderr
r=subprocess.run([str(OUT/'check.exe')],capture_output=True,text=True)
assert r.returncode==0,r.stdout+r.stderr
report={'passed':True,'device_commands':False,'usb_hardware_qualified':False,
 'production_source_sha256':hashlib.sha256((OUT.parent/'OdinRemoteMedia.c').read_bytes()).hexdigest(),
 'checks':['configured file paths','metadata and large file length','multi-chunk reads and byte contents',
 'EOF','seek bounds','partial read failure and cursor','write/create refused','path traversal refused',
 'response identity/CRC','every single-byte wire mutation','every truncated wire response',
 'production handshake with simulated USB events','enumeration before Send','product/ready/start replies',
 'Send failure','event pump failure','enumeration timeout','disconnect abort','sealed transport refused',
 'loader guard installation/idempotence','loader status retained on USB','failed boot replay refused',
 'pre-EBS loader error recovery','no USB recovery after EBS'],
 'result':r.stdout.strip(),'command':cmd}
if options.resident_core7:report['checks']+=['resident core7 live status','resident read state','running kernel relaunch refused']
report['resident_core7_enabled']=options.resident_core7
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
