// SPDX-License-Identifier: BSD-2-Clause-Patent
// Included by the resident USB service only. No arbitrary host address input.
#include <Protocol/GraphicsOutput.h>
#include "OdinKernelSymbols.h"
STATIC UINT64 mCaptureBase,mCaptureBytes;
STATIC UINT32 mCaptureWidth,mCaptureHeight,mCaptureStride,mCaptureFormat;

STATIC VOID InvalidateRead(UINT64 Address,UINT64 Bytes) {
#ifndef ODIN_REMOTE_HOST_TEST
 UINT64 Line,End=Address+Bytes;
 __asm__ volatile("mrs %0,ctr_el0":"=r"(Line));Line=4ULL<<((Line>>16)&15);
 for(Address&=~(Line-1);Address<End;Address+=Line)
  __asm__ volatile("dc ivac,%0"::"r"(Address):"memory");
 __asm__ volatile("dsb sy":::"memory");
#else
 (VOID)Address;(VOID)Bytes;
#endif
}
STATIC VOID *KernelRange(UINT64 Offset,UINT64 Bytes) {
 ODIN_RESIDENT_CONTEXT *C=mResidentContext;
 if(!C || C->VirtualBase!=ODIN_KERNEL_BASE || C->Memory+C->Length<C->Memory ||
    Offset>C->Length || Bytes>C->Length-Offset)return NULL;
 return (VOID*)(UINTN)(C->Memory+Offset);
}
STATIC UINT64 KernelWord(UINT64 Offset,UINTN Bytes) {
 VOID *P=KernelRange(Offset,Bytes);if(!P)return 0;
 InvalidateRead((UINT64)(UINTN)P,Bytes);
 return Bytes==4?ReadUnaligned32(P):ReadUnaligned64(P);
}
STATIC EFI_STATUS KernelStage(VOID) {
 CHAR8 Text[61];
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 AsciiSPrint(Text,sizeof(Text),"stage=%lx midr=%lx",KernelWord(ODIN_STAGE_OFFSET,8),mResidentContext->Midr);
 return Reply("OKAY",Text);
}
STATIC EFI_STATUS KernelPostStage(VOID) {
#ifdef ODIN_POSTVM_OFFSET
 CHAR8 Text[61];
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 AsciiSPrint(Text,sizeof(Text),"stage=%lx caller=%lx",KernelWord(ODIN_POSTVM_OFFSET,8),KernelWord(ODIN_POSTCALLER_OFFSET,8));
 return Reply("OKAY",Text);
#else
 return Reply("FAIL","post-VM counter absent in this kernel");
#endif
}
STATIC EFI_STATUS KernelPanic(VOID) {
#ifdef ODIN_PANIC_STR_OFFSET
 UINT64 VA=KernelWord(ODIN_PANIC_STR_OFFSET,8),Caller=KernelWord(ODIN_PANIC_CALLER_OFFSET,8),At=0;
 CHAR8 Text[61];VOID *P;EFI_STATUS Status;
 AsciiSPrint(Text,sizeof(Text),"panic caller=%lx format=%lx",Caller,VA);
 Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 if(!VA || VA<ODIN_KERNEL_BASE)return Reply("OKAY","no published panic format");
 for(;At<1024;) {UINTN N=0;
  while(N<60 && At<1024) {UINT8 Ch;
   P=KernelRange(VA-ODIN_KERNEL_BASE+At,1);if(!P)return Reply("FAIL","panic text outside owned RAM");
   InvalidateRead((UINT64)(UINTN)P,1);Ch=*(volatile UINT8*)P;if(!Ch)break;
   At++;Text[N++]=(Ch>=32&&Ch<127)||Ch=='\n'?Ch:'.';
  }
  Text[N]=0;Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
  if(N<60)break;
 }
 return Reply("OKAY","panic format complete");
#else
 return Reply("FAIL","panic symbols absent");
#endif
}
STATIC EFI_STATUS TouchStats(VOID) {
#ifdef ODIN_TOUCH_STATS_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(!KernelRange(ODIN_TOUCH_STATS_OFFSET,64))return Reply("FAIL","counters outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"touch[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_TOUCH_STATS_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_TOUCH_STATS_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_TOUCH_STATS_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_TOUCH_STATS_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","touch counters complete");
#else
 return Reply("FAIL","touch counters absent");
#endif
}
STATIC EFI_STATUS PresentStats(VOID) {
#ifdef ODIN_PRESENT_STATS_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(!KernelRange(ODIN_PRESENT_STATS_OFFSET,64))return Reply("FAIL","counters outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"present[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_PRESENT_STATS_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_PRESENT_STATS_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_PRESENT_STATS_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_PRESENT_STATS_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","present counters complete");
#else
 return Reply("FAIL","present counters absent");
#endif
}
STATIC EFI_STATUS SurfaceStats(VOID) {
#ifdef ODIN_SURFACE_STATS_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(!KernelRange(ODIN_SURFACE_STATS_OFFSET,64))return Reply("FAIL","counters outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"surface[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_SURFACE_STATS_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_SURFACE_STATS_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_SURFACE_STATS_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_SURFACE_STATS_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","surface counters complete");
#else
 return Reply("FAIL","surface counters absent");
#endif
}
STATIC EFI_STATUS UiThreads(VOID) {
#ifdef ODIN_UI_THREADS_OFFSET
 STATIC UINT64 Snapshot[1024];
 UINT64 Sequence=0,Bank=0,Count;BOOLEAN Valid=FALSE;CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext || !KernelRange(ODIN_UI_THREADS_OFFSET,2050*8))
  return Reply("FAIL","UI sampler outside owned RAM");
 for(UINT32 Attempt=0;Attempt<3;Attempt++) {
  Sequence=KernelWord(ODIN_UI_THREADS_OFFSET,8);Bank=KernelWord(ODIN_UI_THREADS_OFFSET+8,8);
  if(!Sequence)return Reply("FAIL","UI sampler has no completed sample");
  if(Bank>1)return Reply("FAIL","invalid UI sampler bank");
  VOID *P=KernelRange(ODIN_UI_THREADS_OFFSET+(2+Bank*1024)*8,sizeof(Snapshot));
  InvalidateRead((UINT64)(UINTN)P,sizeof(Snapshot));CopyMem(Snapshot,P,sizeof(Snapshot));
  if(Snapshot[0]==1 && Snapshot[1]==Sequence && Sequence==KernelWord(ODIN_UI_THREADS_OFFSET,8) &&
     Bank==KernelWord(ODIN_UI_THREADS_OFFSET+8,8)) {Valid=TRUE;break;}
 }
 if(!Valid)return Reply("FAIL","UI sampler changed during capture");
 Count=Snapshot[3];if(Count>96)return Reply("FAIL","invalid UI sampler row count");
 AsciiSPrint(Text,sizeof(Text),"ui sequence=%lx count=%u ticks=%lx",Sequence,(UINT32)Count,Snapshot[2]);
 Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 for(UINT32 I=0;I<Count;I++) {
  UINT64 *Row=Snapshot+8+I*9;
  AsciiSPrint(Text,sizeof(Text),"ui[%u]=%lx,%lx,%lx",I,Row[0],Row[1],Row[2]);
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
  AsciiSPrint(Text,sizeof(Text),"uw[%u]=%lx,%lx",I,Row[3],Row[4]);
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
  AsciiSPrint(Text,sizeof(Text),"up[%u]=%lx,%lx",I,Row[5],Row[6]);
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
  AsciiSPrint(Text,sizeof(Text),"us[%u]=%lx,%lx",I,Row[7],Row[8]);
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","UI threads complete");
#else
 return Reply("FAIL","UI sampler absent");
#endif
}
STATIC EFI_STATUS UiPolicy(VOID) {
#ifdef ODIN_UI_POLICY_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext || !KernelRange(ODIN_UI_POLICY_OFFSET,64))
  return Reply("FAIL","UI policy outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"policy[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_UI_POLICY_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_UI_POLICY_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_UI_POLICY_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_UI_POLICY_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","UI policy complete");
#else
 return Reply("FAIL","UI policy absent");
#endif
}
STATIC EFI_STATUS UiPolicyCommand(UINT32 Command) {
#ifdef ODIN_UI_POLICY_COMMAND_OFFSET
 // The only mutation is this fixed RAM fixture flag. No supplied address,
 // code change, input injection or device storage operation is accepted.
 if(Command>1)return Reply("FAIL","invalid UI policy command");
 volatile UINT32 *P=KernelRange(ODIN_UI_POLICY_COMMAND_OFFSET,4);
 if(!P)return Reply("FAIL","UI command outside owned RAM");
 *P=Command;
#ifndef ODIN_REMOTE_HOST_TEST
 __asm__ volatile("dc cvac,%0\n\tdsb sy"::"r"(P):"memory");
#endif
 return Reply("OKAY",Command?"original UI idle reset requested":"UI idle reset disabled");
#else
 return Reply("FAIL","UI policy command absent");
#endif
}
STATIC EFI_STATUS HidStats(VOID) {
#ifdef ODIN_HID_STATS_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(!KernelRange(ODIN_HID_STATS_OFFSET,64))return Reply("FAIL","counters outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"hid[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_HID_STATS_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_HID_STATS_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_HID_STATS_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_HID_STATS_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","hid counters complete");
#else
 return Reply("FAIL","hid counters absent");
#endif
}
STATIC EFI_STATUS GpuStats(VOID) {
#ifdef ODIN_GPU_STATS_OFFSET
 CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(!KernelRange(ODIN_GPU_STATS_OFFSET,64))return Reply("FAIL","counters outside owned RAM");
 for(UINT32 I=0;I<16;I+=4) {
  AsciiSPrint(Text,sizeof(Text),"gpu[%u]=%x,%x,%x,%x",I,
   (UINT32)KernelWord(ODIN_GPU_STATS_OFFSET+I*4,4),
   (UINT32)KernelWord(ODIN_GPU_STATS_OFFSET+(I+1)*4,4),
   (UINT32)KernelWord(ODIN_GPU_STATS_OFFSET+(I+2)*4,4),
   (UINT32)KernelWord(ODIN_GPU_STATS_OFFSET+(I+3)*4,4));
  Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","gpu counters complete");
#else
 return Reply("FAIL","gpu counters absent");
#endif
}
STATIC EFI_STATUS GpuLog(VOID) {
#if defined(ODIN_GPU_LOG_OFFSET) && defined(ODIN_GPU_LOG_USED_OFFSET)
 UINT64 Used=KernelWord(ODIN_GPU_LOG_USED_OFFSET,4),At;CHAR8 Text[61];EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 if(Used>65536 || !KernelRange(ODIN_GPU_LOG_OFFSET,65536))return Reply("FAIL","GPU log outside owned RAM");
 CONST volatile UINT8 *P=KernelRange(ODIN_GPU_LOG_OFFSET,65536);
 InvalidateRead((UINT64)(UINTN)P,Used);
 for(At=Used>8192?Used-8192:0;At<Used;) {UINTN N=0;
  while(N<60 && At<Used){UINT8 Ch=P[At++];Text[N++]=(Ch>=32&&Ch<127)||Ch=='\n'||Ch=='\r'?Ch:'.';}
  Text[N]=0;Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","GPU log complete");
#else
 return Reply("FAIL","GPU log absent");
#endif
}
STATIC EFI_STATUS KernelLog(VOID) {
 UINT64 Base,End,Size,Offset,Bytes,At;CHAR8 Text[61];VOID *P;EFI_STATUS Status;
 if(!mResidentContext)return Reply("FAIL","kernel not started");
 Base=KernelWord(ODIN_LOG_BASE_OFFSET,8);End=KernelWord(ODIN_LOG_PTR_OFFSET,8);
 Size=KernelWord(ODIN_LOG_SIZE_OFFSET,4);
 if(!Base || End<Base || End-Base>MIN(Size,0x100000ULL) || Base<ODIN_KERNEL_BASE)
  return Reply("FAIL","kernel debug buffer not initialized");
 Bytes=End-Base;if(Bytes>8192){Base+=Bytes-8192;Bytes=8192;}
 Offset=Base-ODIN_KERNEL_BASE;P=KernelRange(Offset,Bytes);
 if(!P)return Reply("FAIL","kernel log outside owned RAM");
 InvalidateRead((UINT64)(UINTN)P,Bytes);
 for(At=0;At<Bytes;) {UINTN N=0;
  while(N<60 && At<Bytes){UINT8 Ch=((volatile UINT8*)P)[At++];Text[N++]=(Ch>=32&&Ch<127)||Ch=='\n'||Ch=='\r'?Ch:'.';}
  Text[N]=0;Status=Reply("INFO",Text);if(EFI_ERROR(Status))return Status;
 }
 return Reply("OKAY","kernel log complete");
}
STATIC VOID CaptureInitialize(VOID) {
 EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop=NULL;EFI_GUID Guid=EFI_GRAPHICS_OUTPUT_PROTOCOL_GUID;
 EFI_GRAPHICS_OUTPUT_MODE_INFORMATION *Info;
 if(EFI_ERROR(gBS->LocateProtocol(&Guid,NULL,(VOID**)&Gop)) || !Gop || !Gop->Mode || !Gop->Mode->Info)return;
 Info=Gop->Mode->Info;
 if(!Info->HorizontalResolution || !Info->VerticalResolution || Info->HorizontalResolution>8192 ||
    Info->VerticalResolution>8192 || Info->PixelsPerScanLine<Info->HorizontalResolution || Info->PixelsPerScanLine>8192 ||
    Info->PixelFormat==PixelBltOnly)return;
 mCaptureFormat=Info->PixelFormat;
 if(mCaptureFormat==PixelBitMask) {
  if(Info->PixelInformation.RedMask==0xff0000 && Info->PixelInformation.GreenMask==0xff00 && Info->PixelInformation.BlueMask==0xff)mCaptureFormat=1;
  else if(Info->PixelInformation.RedMask==0xff && Info->PixelInformation.GreenMask==0xff00 && Info->PixelInformation.BlueMask==0xff0000)mCaptureFormat=0;
  else return;
 }
 if(mCaptureFormat>1)return;
 mCaptureBytes=(UINT64)Info->PixelsPerScanLine*4*Info->VerticalResolution;
 if(mCaptureBytes>Gop->Mode->FrameBufferSize || mCaptureBytes>SIZE_64MB ||
    Gop->Mode->FrameBufferBase+mCaptureBytes<Gop->Mode->FrameBufferBase){mCaptureBytes=0;return;}
 mCaptureBase=Gop->Mode->FrameBufferBase;mCaptureWidth=Info->HorizontalResolution;
 mCaptureHeight=Info->VerticalResolution;mCaptureStride=Info->PixelsPerScanLine*4;
}
STATIC EFI_STATUS CaptureInfo(VOID) {
 CHAR8 Text[61];if(!mCaptureBase || !mCaptureBytes)return Reply("FAIL","GOP capture unavailable");
 AsciiSPrint(Text,sizeof(Text),"%u:%u:%u:%u:%u",mCaptureWidth,mCaptureHeight,mCaptureStride,mCaptureFormat,(UINT32)mCaptureBytes);
 return Reply("OKAY",Text);
}
STATIC EFI_STATUS CaptureUpload(VOID) {
 UINT64 At;UINTN N;EFI_STATUS Status;
 if(!mCaptureBase || !mCaptureBytes)return Reply("FAIL","GOP capture unavailable");
 Status=DataReply((UINTN)mCaptureBytes);if(EFI_ERROR(Status))return Status;
 for(At=0;At<mCaptureBytes;At+=N){
  N=(UINTN)MIN(CHUNK,mCaptureBytes-At);
  // The only non-kernel range exposed is the framebuffer reported by GOP.
  CopyMem(mTx,(VOID*)(UINTN)(mCaptureBase+At),N);
  if(Transfer(IN_EP,N)!=(INTN)N)return EFI_DEVICE_ERROR;
 }
 return Reply("OKAY","");
}
