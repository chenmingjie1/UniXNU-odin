// SPDX-License-Identifier: BSD-2-Clause-Patent
// Read-only UEFI files backed by bounded USB requests to the paired computer.
// USB ABI and descriptor layout come from the measured odin vendor driver and
// the previously working loader; no storage writes or arbitrary memory access.
#include <Uefi.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/DevicePath.h>
#include <Protocol/UniXNULoader.h>
#include <Protocol/EFIUsbDevice.h>
#include <Guid/FileInfo.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/PrintLib.h>
#include "OdinRemoteProtocol.h"
#ifdef ODIN_RESIDENT_CORE7
#include "OdinResident.h"
#endif

#define CHUNK SIZE_1MB
#define OUT_EP 0x01
#define IN_EP 0x81
typedef struct { CONST CHAR16 *Path; UINT64 Bytes; } REMOTE_FILE;
#include "OdinRemoteFiles.h"
STATIC EFI_GUID mUsbGuid={0xd9d9ce48,0x44b8,0x4f49,{0x8e,0x3e,0x2a,0x3b,0x92,0x7d,0xc6,0xc1}};
STATIC EFI_GUID mUsbInit={0x1c0cffce,0xfc8d,0x4e44,{0x8c,0x78,0x9c,0x9e,0x5b,0x53,0x0d,0x36}};
STATIC EFI_USB_DEVICE_PROTOCOL *mUsb;
STATIC UINT8 *mRx,*mTx,*mIncoming;
STATIC BOOLEAN mStarted,mSealed,mConnected;
STATIC UINT32 mSequence,mFileId;
STATIC UINT64 mOffset,mReadCount,mTransferred;
STATIC UINTN mWanted;
STATIC CHAR8 mLast[64]="waiting";
STATIC CHAR8 mBootStatus[64]="bds:starting";
STATIC BOOLEAN mRecovering;
STATIC UNIXNU_LOADER_BOOT mOriginalBoot;
#ifdef ODIN_RESIDENT_CORE7
STATIC ODIN_RESIDENT_CONTEXT *mResidentContext;
STATIC VOID ResidentStatus(VOID) {
 ODIN_RESIDENT_CONTEXT *Context=mResidentContext;
 UINT64 At,Line;
 if(!Context)return;
#ifndef ODIN_REMOTE_HOST_TEST
 __asm__ volatile("mrs %0,ctr_el0":"=r"(Line));Line=4ULL<<((Line>>16)&15);
 At=(UINT64)(UINTN)&Context->Entered;At&=~(Line-1);
 for(;At<(UINT64)(UINTN)(Context+1);At+=Line)
  __asm__ volatile("dc ivac,%0"::"r"(At):"memory");
 __asm__ volatile("dsb sy":::"memory");
#else
 (VOID)At;(VOID)Line;
#endif
 AsciiSPrint(mBootStatus,sizeof(mBootStatus),"core7:entered=%lx:fault=%lx",Context->Entered,Context->Fault);
}
#endif
STATIC CONST UINT8 mDevice[]={18,1,0x10,2,0,0,0,64,0xd1,0x18,0x0d,0xd0,0,1,1,2,3,1};
STATIC CONST UINT8 mSsDevice[]={18,1,0,3,0,0,0,9,0xd1,0x18,0x0d,0xd0,0,1,1,2,3,1};
STATIC CONST UINT8 mConfig[]={9,2,32,0,1,1,0,0x80,0x50,9,4,0,0,2,0xff,0x42,3,4,7,5,IN_EP,2,0,2,0,7,5,OUT_EP,2,0,2,0};
STATIC CONST UINT8 mSsConfig[]={9,2,44,0,1,1,0,0x80,0x10,9,4,0,0,2,0xff,0x42,3,4,7,5,IN_EP,2,0,4,0,6,0x30,4,0,0,0,7,5,OUT_EP,2,0,4,0,6,0x30,4,0,0,0};
STATIC CONST UINT8 mQualifier[]={10,6,0,2,0xff,0xff,0xff,64,1,0};
STATIC CONST UINT8 mBos[]={5,0xf,42,0,3,7,0x10,2,6,0,0,0,10,0x10,3,0,0xe,0,1,7,0x65,0,20,0x10,0xa,0,1,0,0,0,0,0x11,0,0,0x30,0x40,0xa,0,0xb0,0x40,0xa,0};
STATIC CONST UINT8 mLang[]={4,3,9,4};
STATIC CONST UINT8 mManufacturer[]={8,3,'X',0,'N',0,'U',0};
STATIC CONST UINT8 mProduct[]={14,3,'U',0,'n',0,'i',0,'X',0,'N',0,'U',0};
STATIC CONST UINT8 mSerial[]={32,3,'o',0,'d',0,'i',0,'n',0,'-',0,'u',0,'n',0,'i',0,'x',0,'n',0,'u',0,'-',0,'u',0,'6',0,'4',0};
STATIC CONST UINT8 mInterface[]={18,3,'f',0,'a',0,'s',0,'t',0,'b',0,'o',0,'o',0,'t',0};
#ifndef ODIN_REMOTE_HOST_TEST
STATIC UINT64 Counter(VOID){UINT64 v;__asm__ volatile("mrs %0,cntvct_el0":"=r"(v));return v;}
STATIC UINT64 Frequency(VOID){UINT64 v;__asm__ volatile("mrs %0,cntfrq_el0":"=r"(v));return v;}
#else
STATIC UINT64 mHostCounter,mHostCounterStep=1;
STATIC UINT64 Counter(VOID){mHostCounter+=mHostCounterStep;return mHostCounter;}
STATIC UINT64 Frequency(VOID){return 19200000;}
STATIC EFI_STATUS HostReadChunk(VOID *Destination);
#endif
STATIC VOID EFIAPI Notify(EFI_EVENT Event,VOID *Context){(VOID)Event;(VOID)Context;}

STATIC EFI_STATUS StartUsb(VOID) {
 EFI_STATUS s;EFI_EVENT event;STATIC VOID *cfg=(VOID*)mConfig,*ss=(VOID*)mSsConfig;
 STATIC EFI_USB_STRING_DESCRIPTOR *strings[5];STATIC USB_DEVICE_DESCRIPTOR_SET set;
 if(mSealed)return EFI_UNSUPPORTED;
 if(mStarted)return EFI_SUCCESS;
 s=gBS->CreateEventEx(EVT_NOTIFY_SIGNAL,TPL_CALLBACK,Notify,NULL,&mUsbInit,&event);
 if(!EFI_ERROR(s)){gBS->SignalEvent(event);gBS->CloseEvent(event);}
 s=gBS->LocateProtocol(&mUsbGuid,NULL,(VOID**)&mUsb);if(EFI_ERROR(s))return s;
 strings[0]=(VOID*)mLang;strings[1]=(VOID*)mManufacturer;strings[2]=(VOID*)mProduct;
 strings[3]=(VOID*)mSerial;strings[4]=(VOID*)mInterface;
 set.DeviceDescriptor=(VOID*)mDevice;set.Descriptors=&cfg;set.SSDeviceDescriptor=(VOID*)mSsDevice;
 set.SSDescriptors=&ss;set.DeviceQualifierDescriptor=(VOID*)mQualifier;set.BinaryDeviceOjectStore=(VOID*)mBos;
 set.StringDescriptorCount=5;set.StringDescritors=strings;
 s=mUsb->StartEx(&set);if(EFI_ERROR(s))return s;
 s=mUsb->AllocateTransferBuffer(CHUNK,(VOID**)&mRx);if(EFI_ERROR(s))return s;
 s=mUsb->AllocateTransferBuffer(CHUNK,(VOID**)&mTx);if(EFI_ERROR(s))return s;
 mIncoming=AllocatePool(CHUNK+32);if(!mIncoming)return EFI_OUT_OF_RESOURCES;
 mStarted=TRUE;return EFI_SUCCESS;
}

// The vendor driver needs its event pump to complete enumeration before Send.
// The working odin loader likewise queues OUT only after Connected is reported.
STATIC EFI_STATUS WaitForConnection(VOID) {
 UINT64 began=Counter(),limit=Frequency()*90;EFI_STATUS s;
 while(!mConnected){USB_DEVICE_EVENT event=UsbDeviceEventNoEvent;UINTN size=sizeof(USB_DEVICE_EVENT_DATA);USB_DEVICE_EVENT_DATA data;
  s=mUsb->HandleEvent(&event,&size,&data);if(EFI_ERROR(s))return s;
  if(event==UsbDeviceEventDeviceStateChange)mConnected=data.DeviceState==UsbDeviceStateConnected;
  if(Counter()-began>limit)return EFI_TIMEOUT;
  if(!mConnected)gBS->Stall(20);
 }
 return EFI_SUCCESS;
}
STATIC INTN Transfer(UINT8 Endpoint,UINTN Bytes) {
 UINT64 began=Counter(),limit=Frequency()*90;EFI_STATUS s;
 s=WaitForConnection();if(EFI_ERROR(s))return -1;
 began=Counter();
 s=mUsb->Send(Endpoint,Bytes,Endpoint==IN_EP?mTx:mRx);if(EFI_ERROR(s))return -1;
 for(;;){USB_DEVICE_EVENT event=UsbDeviceEventNoEvent;UINTN size=sizeof(USB_DEVICE_EVENT_DATA);USB_DEVICE_EVENT_DATA data;
  s=mUsb->HandleEvent(&event,&size,&data);if(EFI_ERROR(s))break;
  if(event==UsbDeviceEventDeviceStateChange){
   mConnected=data.DeviceState==UsbDeviceStateConnected;if(!mConnected)break;
  }
  if(event==UsbDeviceEventTransferNotification && data.TransferOutcome.EndpointIndex==Endpoint){
   if(data.TransferOutcome.Status==UsbDeviceTransferStatusCompleteOK && data.TransferOutcome.BytesCompleted<=Bytes)
    return (INTN)data.TransferOutcome.BytesCompleted;
   break;
  }
  if(Counter()-began>limit
#ifdef ODIN_RESIDENT_CORE7
     && !(mResidentContext && Endpoint==OUT_EP)
#endif
     )break;
  gBS->Stall(20);
 }
 mUsb->AbortXfer(Endpoint);return -1;
}
STATIC EFI_STATUS Reply(CONST CHAR8 *Code,CONST CHAR8 *Text) {
 UINTN n=AsciiSPrint((CHAR8*)mTx,64,"%a%a",Code,Text);
 return Transfer(IN_EP,n)==(INTN)n?EFI_SUCCESS:EFI_DEVICE_ERROR;
}
STATIC EFI_STATUS DataReply(UINTN Bytes) {
 AsciiSPrint((CHAR8*)mTx,16,"DATA%08x",(UINT32)Bytes);
 return Transfer(IN_EP,12)==12?EFI_SUCCESS:EFI_DEVICE_ERROR;
}
VOID OdinRemoteBootStatus(CONST CHAR8 *Stage,EFI_STATUS Status) {
 AsciiSPrint(mBootStatus,sizeof(mBootStatus),"%a:%016lx",Stage,(UINT64)Status);
}
#ifdef ODIN_KERNEL_READBACK
#include "OdinKernelReadback.h"
#endif
// Called by the BDS handoff before launching the actual UniXNU manager. This
// explicit handshake starts and pumps USB even before a filesystem is opened.
EFI_STATUS OdinRemoteHandshake(VOID) {
 EFI_STATUS s;INTN count;CHAR8 command[65];
 s=StartUsb();if(EFI_ERROR(s))return s;
 for(;;){
  count=Transfer(OUT_EP,64);if(count<=0)return EFI_TIMEOUT;
  CopyMem(command,mRx,(UINTN)count);command[count]=0;
  if(!AsciiStrCmp(command,"getvar:product"))s=Reply("OKAY","odin-unixnu-u64");
  else if(!AsciiStrCmp(command,"getvar:odin-read"))s=Reply("OKAY",
#ifdef ODIN_RESIDENT_CORE7
   mResidentContext?"idle:kernel-core7":
#endif
   mRecovering?"idle:uefi-stopped":"idle:desktop-ready");
  else if(!AsciiStrCmp(command,"getvar:result")){
#ifdef ODIN_RESIDENT_CORE7
   ResidentStatus();
#endif
   s=Reply("OKAY",mBootStatus);
  }
#ifdef ODIN_KERNEL_READBACK
  else if(!AsciiStrCmp(command,"getvar:kernel-stage"))s=KernelStage();
  else if(!AsciiStrCmp(command,"getvar:kernel-postvm"))s=KernelPostStage();
  else if(!AsciiStrCmp(command,"oem kernel-panic"))s=KernelPanic();
  else if(!AsciiStrCmp(command,"oem kernel-log"))s=KernelLog();
  else if(!AsciiStrCmp(command,"oem touch-stats"))s=TouchStats();
  else if(!AsciiStrCmp(command,"oem hid-stats"))s=HidStats();
  else if(!AsciiStrCmp(command,"oem gpu-stats"))s=GpuStats();
  else if(!AsciiStrCmp(command,"oem present-stats"))s=PresentStats();
  else if(!AsciiStrCmp(command,"oem surface-stats"))s=SurfaceStats();
  else if(!AsciiStrCmp(command,"oem ui-threads"))s=UiThreads();
  else if(!AsciiStrCmp(command,"oem ui-policy"))s=UiPolicy();
  else if(!AsciiStrCmp(command,"oem ui-wake"))s=UiPolicyCommand(1);
  else if(!AsciiStrCmp(command,"oem ui-idle"))s=UiPolicyCommand(0);
  else if(!AsciiStrCmp(command,"oem gpu-log"))s=GpuLog();
  else if(!AsciiStrCmp(command,"getvar:framebuffer"))s=CaptureInfo();
  else if(!AsciiStrCmp(command,"upload"))s=CaptureUpload();
#endif
  else if(!AsciiStrCmp(command,"oem desktop")){
#ifdef ODIN_RESIDENT_CORE7
   if(mResidentContext)s=Reply("FAIL","kernel already running; reboot required");
   else
#endif
   if(mRecovering)s=Reply("FAIL","failed boot retained; reboot required");
   else return Reply("OKAY","starting native desktop");
  }
  else if(!AsciiStrCmp(command,"reboot")){
   Reply("OKAY","");gBS->Stall(200000);gRT->ResetSystem(EfiResetCold,EFI_SUCCESS,0,NULL);return EFI_ABORTED;
  } else s=Reply("FAIL","waiting for desktop host");
  if(EFI_ERROR(s))return s;
 }
}
#ifdef ODIN_RESIDENT_CORE7
STATIC VOID EFIAPI ResidentRun(ODIN_RESIDENT_CONTEXT *Context) {
 mResidentContext=Context;
#ifdef ODIN_KERNEL_READBACK
 CaptureInitialize();
#endif
 // This is the polling USB path used before EBS, retained on core0. Do not
 // draw to the framebuffer, enable firmware IRQs, or launch another kernel.
 for(;;) {
  ResidentStatus();
  OdinRemoteHandshake();
 }
}
STATIC EFI_GUID mResidentGuid=ODIN_RESIDENT_PROTOCOL_GUID;
STATIC ODIN_RESIDENT_PROTOCOL mResident={ODIN_RESIDENT_REVISION,ResidentRun};
#endif
// Only entered while firmware services still exist. It cannot recover an XNU
// hang after ExitBootServices. Never start the failed payload a second time.
VOID OdinRemoteRecovery(VOID) {
 mRecovering=TRUE;
 while(!mSealed){OdinRemoteHandshake();gBS->Stall(100000);}
}
STATIC EFI_STATUS EFIAPI GuardedBoot(UNIXNU_LOADER_PROTOCOL *This,CONST UNIXNU_LOADER_BOOT_REQUEST *Request) {
 EFI_STATUS s=mOriginalBoot(This,Request);
 if(!mSealed){OdinRemoteBootStatus("darwin-return",s);OdinRemoteRecovery();}
 return s;
}
EFI_STATUS OdinRemoteInstallLoaderGuard(VOID) {
 STATIC EFI_GUID guid=UNIXNU_LOADER_PROTOCOL_GUID;
 UNIXNU_LOADER_PROTOCOL *loader=NULL;EFI_STATUS s;
 s=gBS->LocateProtocol(&guid,NULL,(VOID**)&loader);if(EFI_ERROR(s))return s;
 if(!loader || !loader->Boot || (loader->Revision!=UNIXNU_LOADER_REVISION && loader->Revision!=UNIXNU_LOADER_REVISION_1))return EFI_UNSUPPORTED;
 if(loader->Boot!=GuardedBoot){mOriginalBoot=loader->Boot;loader->Boot=GuardedBoot;}
 return EFI_SUCCESS;
}
STATIC EFI_STATUS RemoteChunk(VOID *Destination) {
#ifdef ODIN_REMOTE_HOST_TEST
 return HostReadChunk(Destination);
#else
 EFI_STATUS s;CHAR8 command[65],reply[64];INTN count;UINTN total,got,n;
 s=StartUsb();if(EFI_ERROR(s))return s;
 ++mSequence;
 for(;;){
  count=Transfer(OUT_EP,64);if(count<=0)return EFI_TIMEOUT;
  CopyMem(command,mRx,(UINTN)count);command[count]=0;
  if(AsciiStrCmp(command,"getvar:product")==0){s=Reply("OKAY","odin-unixnu-u64");}
  else if(AsciiStrCmp(command,"getvar:max-download-size")==0){s=Reply("OKAY","0x00100020");}
  else if(AsciiStrCmp(command,"getvar:odin-read")==0){
   AsciiSPrint(reply,sizeof(reply),"%08x:%08x:%016lx:%08x",mSequence,mFileId,mOffset,(UINT32)mWanted);
   s=Reply("OKAY",reply);
  } else if(AsciiStrCmp(command,"getvar:result")==0){s=Reply("OKAY",mLast);}
  else if(AsciiStrCmp(command,"reboot")==0){
   Reply("OKAY","");gBS->Stall(200000);gRT->ResetSystem(EfiResetCold,EFI_SUCCESS,0,NULL);return EFI_ABORTED;
  } else if(AsciiStrnCmp(command,"download:",9)==0){
   if(AsciiStrLen(command)!=17){Reply("FAIL","bad size format");continue;}
   total=0;for(n=9;n<17;n++){CHAR8 c=command[n];UINTN digit;
    if(c>='0'&&c<='9')digit=c-'0';else if(c>='a'&&c<='f')digit=c-'a'+10;
    else if(c>='A'&&c<='F')digit=c-'A'+10;else break;
    total=(total<<4)|digit;
   }
   if(n!=17 || total!=mWanted+32 || total>CHUNK+32){Reply("FAIL","unexpected response length");continue;}
   s=DataReply(total);if(EFI_ERROR(s))return s;
   got=0;while(got<total){count=Transfer(OUT_EP,MIN(CHUNK,total-got));if(count<=0)return EFI_DEVICE_ERROR;
    CopyMem(mIncoming+got,mRx,(UINTN)count);got+=(UINTN)count;
   }
   s=OdinValidateResponse(mIncoming,total,mSequence,mFileId,mOffset,mWanted);
   if(EFI_ERROR(s)){Reply("FAIL","response identity or CRC mismatch");return s;}
   CopyMem(Destination,mIncoming+32,mWanted);mReadCount++;mTransferred+=mWanted;
   AsciiSPrint(mLast,sizeof(mLast),"read:%x:%lx:%x",mFileId,mOffset,(UINT32)mWanted);
   return Reply("OKAY","");
  } else {s=Reply("FAIL","read-only media: command disabled");}
  if(EFI_ERROR(s))return s;
 }
#endif
}

typedef struct {EFI_FILE_PROTOCOL Io;UINTN Id;UINT64 Position;} OPEN_FILE;
STATIC EFI_STATUS EFIAPI Open(EFI_FILE_PROTOCOL*,EFI_FILE_PROTOCOL**,CHAR16*,UINT64,UINT64);
STATIC EFI_STATUS EFIAPI Close(EFI_FILE_PROTOCOL *Io){FreePool(Io);return EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI Delete(EFI_FILE_PROTOCOL *Io){Close(Io);return EFI_WARN_DELETE_FAILURE;}
STATIC EFI_STATUS EFIAPI Write(EFI_FILE_PROTOCOL *Io,UINTN *Size,VOID *Buffer){(VOID)Io;(VOID)Size;(VOID)Buffer;return EFI_WRITE_PROTECTED;}
STATIC EFI_STATUS EFIAPI SetInfo(EFI_FILE_PROTOCOL *Io,EFI_GUID *Guid,UINTN Size,VOID *Buffer){(VOID)Io;(VOID)Guid;(VOID)Size;(VOID)Buffer;return EFI_WRITE_PROTECTED;}
STATIC EFI_STATUS EFIAPI Flush(EFI_FILE_PROTOCOL *Io){(VOID)Io;return EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI GetPosition(EFI_FILE_PROTOCOL *Io,UINT64 *Position){if(!Position)return EFI_INVALID_PARAMETER;*Position=((OPEN_FILE*)Io)->Position;return EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI SetPosition(EFI_FILE_PROTOCOL *Io,UINT64 Position){
 OPEN_FILE *f=(VOID*)Io;if(f->Id<4 && Position)return EFI_UNSUPPORTED;
 if(Position==MAX_UINT64)Position=mFiles[f->Id].Bytes;
 if(Position>mFiles[f->Id].Bytes)return EFI_INVALID_PARAMETER;f->Position=Position;return EFI_SUCCESS;
}
STATIC CONST CHAR16 *BaseName(UINTN Id){CONST CHAR16 *p=mFiles[Id].Path,*last=p;while(*p){if(*p==L'\\')last=p+1;p++;}return last;}
STATIC EFI_STATUS FileInfo(UINTN Id,UINTN *Size,VOID *Buffer){
 UINTN need=SIZE_OF_EFI_FILE_INFO+StrSize(BaseName(Id));EFI_FILE_INFO *info=Buffer;
 if(!Size)return EFI_INVALID_PARAMETER;
 if(!Buffer || *Size<need){*Size=need;return EFI_BUFFER_TOO_SMALL;}
 ZeroMem(Buffer,need);info->Size=need;info->FileSize=mFiles[Id].Bytes;info->PhysicalSize=mFiles[Id].Bytes;
 info->Attribute=EFI_FILE_READ_ONLY|(Id<4?EFI_FILE_DIRECTORY:0);CopyMem(info->FileName,BaseName(Id),StrSize(BaseName(Id)));*Size=need;return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI GetInfo(EFI_FILE_PROTOCOL *Io,EFI_GUID *Guid,UINTN *Size,VOID *Buffer){
 if(!Guid || !CompareGuid(Guid,&gEfiFileInfoGuid))return EFI_UNSUPPORTED;
 return FileInfo(((OPEN_FILE*)Io)->Id,Size,Buffer);
}
STATIC EFI_STATUS EFIAPI Read(EFI_FILE_PROTOCOL *Io,UINTN *Size,VOID *Buffer){
 OPEN_FILE *f=(VOID*)Io;UINTN done=0,want;EFI_STATUS s;
 if(!Size || (!Buffer && *Size))return EFI_INVALID_PARAMETER;
 if(f->Id<4){*Size=0;return EFI_SUCCESS;} // Directory enumeration is unnecessary for fixed configured paths.
 want=(UINTN)MIN((UINT64)*Size,mFiles[f->Id].Bytes-f->Position);
 while(done<want){mWanted=MIN(CHUNK,want-done);mFileId=(UINT32)f->Id;mOffset=f->Position;
  s=RemoteChunk((UINT8*)Buffer+done);if(EFI_ERROR(s)){*Size=done;return s;}
  done+=mWanted;f->Position+=mWanted;
 }
 *Size=done;return EFI_SUCCESS;
}
STATIC EFI_STATUS NewFile(UINTN Id,EFI_FILE_PROTOCOL **Out){
 OPEN_FILE *f;if(!Out)return EFI_INVALID_PARAMETER;*Out=NULL;f=AllocateZeroPool(sizeof(*f));if(!f)return EFI_OUT_OF_RESOURCES;
 f->Id=Id;f->Io.Revision=EFI_FILE_PROTOCOL_REVISION;f->Io.Open=Open;f->Io.Close=Close;f->Io.Delete=Delete;
 f->Io.Read=Read;f->Io.Write=Write;f->Io.GetPosition=GetPosition;f->Io.SetPosition=SetPosition;
 f->Io.GetInfo=GetInfo;f->Io.SetInfo=SetInfo;f->Io.Flush=Flush;*Out=&f->Io;return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Open(EFI_FILE_PROTOCOL *Io,EFI_FILE_PROTOCOL **Out,CHAR16 *Name,UINT64 Mode,UINT64 Attributes){
 CHAR16 path[260];UINTN pos=0,i,id;OPEN_FILE *f=(VOID*)Io;(VOID)Attributes;
 if(!Out || !Name)return EFI_INVALID_PARAMETER;*Out=NULL;
 if(Mode!=EFI_FILE_MODE_READ)return EFI_WRITE_PROTECTED;
 if(f->Id>=4)return EFI_UNSUPPORTED;
 if(Name[0]!=L'\\' && Name[0]!=L'/'){pos=StrLen(mFiles[f->Id].Path);CopyMem(path,mFiles[f->Id].Path,pos*sizeof(CHAR16));}
 if(!pos || path[pos-1]!=L'\\')path[pos++]=L'\\';
 for(i=0;Name[i];i++){CHAR16 c=Name[i]==L'/'?L'\\':Name[i];if(c==L'\\' && pos && path[pos-1]==c)continue;
  if(pos>=ARRAY_SIZE(path)-1 || (c==L'.'&&(!Name[i+1]||Name[i+1]==L'.'||Name[i+1]==L'\\')))return EFI_NOT_FOUND;
  path[pos++]=c;
 }
 if(pos>1 && path[pos-1]==L'\\')pos--;path[pos]=0;
 for(id=0;id<ARRAY_SIZE(mFiles);id++){if(StrCmp(path,mFiles[id].Path)==0)return NewFile(id,Out);}
 return EFI_NOT_FOUND;
}
STATIC EFI_STATUS EFIAPI OpenVolume(EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *This,EFI_FILE_PROTOCOL **Root){(VOID)This;return NewFile(0,Root);}
STATIC EFI_SIMPLE_FILE_SYSTEM_PROTOCOL mFs={EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_REVISION,OpenVolume};
STATIC struct {VENDOR_DEVICE_PATH Vendor;EFI_DEVICE_PATH_PROTOCOL End;} mPath={
 {{HARDWARE_DEVICE_PATH,HW_VENDOR_DP,{sizeof(VENDOR_DEVICE_PATH),0}},
 {0xabee649a,0x4b85,0x4776,{0x83,0x50,0x64,0x64,0x50,0x4d,0x45,0x44}}},
 {END_DEVICE_PATH_TYPE,END_ENTIRE_DEVICE_PATH_SUBTYPE,{sizeof(EFI_DEVICE_PATH_PROTOCOL),0}}};
STATIC VOID EFIAPI ExitBoot(EFI_EVENT Event,VOID *Context){(VOID)Event;(VOID)Context;mSealed=TRUE;}
EFI_STATUS EFIAPI OdinRemoteMediaEntry(EFI_HANDLE Image,EFI_SYSTEM_TABLE *System){
 EFI_HANDLE handle=NULL;EFI_EVENT event;EFI_STATUS s;(VOID)Image;(VOID)System;
 s=gBS->CreateEvent(EVT_SIGNAL_EXIT_BOOT_SERVICES,TPL_NOTIFY,ExitBoot,NULL,&event);if(EFI_ERROR(s))return s;
 s=gBS->InstallMultipleProtocolInterfaces(&handle,&gEfiSimpleFileSystemProtocolGuid,&mFs,&gEfiDevicePathProtocolGuid,&mPath,NULL);
#ifdef ODIN_RESIDENT_CORE7
 if(!EFI_ERROR(s))s=gBS->InstallMultipleProtocolInterfaces(&handle,&mResidentGuid,&mResident,NULL);
#endif
 Print(L"ODINREMOTE: read-only USB filesystem installed: %r\n",s);return s;
}
