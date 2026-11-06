"""Run the actual bounded kernel readback and GOP capture callbacks on host RAM."""
from pathlib import Path
import argparse,hashlib,json,subprocess
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag',default='u70');options=parser.parse_args();assert options.tag.isalnum()
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
OUT=DEV/('build/remote-media-'+options.tag+'/readback-check');OUT.mkdir(exist_ok=True)
source=r'''
#define ODIN_REMOTE_HOST_TEST
#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/PrintLib.h>
#include <Protocol/GraphicsOutput.h>
#include "OdinResident.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define CHUNK 16
#define IN_EP 0x81
static UINT8 tx[CHUNK];static UINT8 *mTx=tx;
static ODIN_RESIDENT_CONTEXT *mResidentContext;
static char lastCode[8],lastText[128],logText[32768];static UINTN logBytes;
static UINT8 wire[128];static UINTN wireBytes,expectedBytes;static int failTransfer;
EFI_BOOT_SERVICES services,*gBS=&services;
VOID *EFIAPI CopyMem(VOID *d,CONST VOID *s,UINTN n){return memcpy(d,s,n);}
UINT32 EFIAPI ReadUnaligned32(CONST VOID *p){UINT32 v;memcpy(&v,p,4);return v;}
UINT64 EFIAPI ReadUnaligned64(CONST VOID *p){UINT64 v;memcpy(&v,p,8);return v;}
UINTN EFIAPI AsciiSPrint(CHAR8 *out,UINTN size,CONST CHAR8 *fmt,...){
 va_list a;va_start(a,fmt);int n;
 if(!strcmp(fmt,"stage=%lx midr=%lx")||!strcmp(fmt,"stage=%lx caller=%lx")||!strcmp(fmt,"panic caller=%lx format=%lx")){UINT64 x=va_arg(a,UINT64),y=va_arg(a,UINT64);const char *converted=!strcmp(fmt,"stage=%lx midr=%lx")?"stage=%llx midr=%llx":!strcmp(fmt,"stage=%lx caller=%lx")?"stage=%llx caller=%llx":"panic caller=%llx format=%llx";n=snprintf(out,size,converted,(unsigned long long)x,(unsigned long long)y);}
 else if(!strcmp(fmt,"ui sequence=%lx count=%u ticks=%lx")){UINT64 x=va_arg(a,UINT64);unsigned y=va_arg(a,unsigned);UINT64 z=va_arg(a,UINT64);n=snprintf(out,size,"ui sequence=%llx count=%u ticks=%llx",(unsigned long long)x,y,(unsigned long long)z);}
 else if(!strncmp(fmt,"ui[",3)){unsigned i=va_arg(a,unsigned);UINT64 x=va_arg(a,UINT64),y=va_arg(a,UINT64),z=va_arg(a,UINT64);n=snprintf(out,size,"ui[%u]=%llx,%llx,%llx",i,(unsigned long long)x,(unsigned long long)y,(unsigned long long)z);}
 else if(!strncmp(fmt,"uw[",3)||!strncmp(fmt,"up[",3)||!strncmp(fmt,"us[",3)){unsigned i=va_arg(a,unsigned);UINT64 x=va_arg(a,UINT64),y=va_arg(a,UINT64);char converted[40];snprintf(converted,sizeof(converted),"%c%c[%%u]=%%llx,%%llx",fmt[0],fmt[1]);n=snprintf(out,size,converted,i,(unsigned long long)x,(unsigned long long)y);}
 else {unsigned x=va_arg(a,unsigned),y=va_arg(a,unsigned),z=va_arg(a,unsigned),w=va_arg(a,unsigned),v=va_arg(a,unsigned);
  if(!strcmp(fmt,"touch[%u]=%x,%x,%x,%x")||!strcmp(fmt,"hid[%u]=%x,%x,%x,%x")||!strcmp(fmt,"gpu[%u]=%x,%x,%x,%x")||!strcmp(fmt,"present[%u]=%x,%x,%x,%x")||!strcmp(fmt,"surface[%u]=%x,%x,%x,%x")||!strcmp(fmt,"policy[%u]=%x,%x,%x,%x"))n=snprintf(out,size,fmt,x,y,z,w,v);
  else {assert(!strcmp(fmt,"%u:%u:%u:%u:%u"));n=snprintf(out,size,"%u:%u:%u:%u:%u",x,y,z,w,v);}}
 va_end(a);assert(n>=0 && (UINTN)n<size);return n;
}
STATIC EFI_STATUS Reply(CONST CHAR8 *code,CONST CHAR8 *text){
 assert(strlen(text)<=60);strcpy(lastCode,code);strcpy(lastText,text);
 if(!strcmp(code,"INFO")){UINTN n=strlen(text);assert(logBytes+n<sizeof(logText));memcpy(logText+logBytes,text,n);logBytes+=n;}
 return EFI_SUCCESS;
}
STATIC EFI_STATUS DataReply(UINTN n){expectedBytes=n;return EFI_SUCCESS;}
STATIC INTN Transfer(UINT8 ep,UINTN n){assert(ep==IN_EP && n<=CHUNK);if(failTransfer)return -1;assert(wireBytes+n<=sizeof(wire));memcpy(wire+wireBytes,mTx,n);wireBytes+=n;return n;}
#include "OdinKernelReadback.h"
static EFI_GRAPHICS_OUTPUT_PROTOCOL gop;static EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE mode;static EFI_GRAPHICS_OUTPUT_MODE_INFORMATION info;
static EFI_STATUS EFIAPI Locate(EFI_GUID *guid,VOID *registration,VOID **out){EFI_GUID expected=EFI_GRAPHICS_OUTPUT_PROTOCOL_GUID;assert(!memcmp(guid,&expected,16));(void)registration;*out=&gop;return EFI_SUCCESS;}
static void put64(UINT8 *mem,UINT64 off,UINT64 value){memcpy(mem+off,&value,8);}
int main(void){
 ODIN_RESIDENT_CONTEXT context={0};UINT64 highest=ODIN_STAGE_OFFSET;
 UINT64 offsets[]={ODIN_LOG_BASE_OFFSET,ODIN_LOG_PTR_OFFSET,ODIN_LOG_SIZE_OFFSET};
 for(UINTN i=0;i<3;i++)if(offsets[i]>highest)highest=offsets[i];
#ifdef ODIN_POSTVM_OFFSET
 if(ODIN_POSTVM_OFFSET>highest)highest=ODIN_POSTVM_OFFSET;
 if(ODIN_POSTCALLER_OFFSET>highest)highest=ODIN_POSTCALLER_OFFSET;
#endif
#ifdef ODIN_PANIC_STR_OFFSET
 if(ODIN_PANIC_STR_OFFSET>highest)highest=ODIN_PANIC_STR_OFFSET;
 if(ODIN_PANIC_CALLER_OFFSET>highest)highest=ODIN_PANIC_CALLER_OFFSET;
#endif
#ifdef ODIN_TOUCH_STATS_OFFSET
 if(ODIN_TOUCH_STATS_OFFSET+64>highest)highest=ODIN_TOUCH_STATS_OFFSET+64;
#endif
#ifdef ODIN_HID_STATS_OFFSET
 if(ODIN_HID_STATS_OFFSET+64>highest)highest=ODIN_HID_STATS_OFFSET+64;
#endif
#ifdef ODIN_GPU_STATS_OFFSET
 if(ODIN_GPU_STATS_OFFSET+64>highest)highest=ODIN_GPU_STATS_OFFSET+64;
#endif
#ifdef ODIN_PRESENT_STATS_OFFSET
 if(ODIN_PRESENT_STATS_OFFSET+64>highest)highest=ODIN_PRESENT_STATS_OFFSET+64;
#endif
#ifdef ODIN_SURFACE_STATS_OFFSET
 if(ODIN_SURFACE_STATS_OFFSET+64>highest)highest=ODIN_SURFACE_STATS_OFFSET+64;
#endif
#ifdef ODIN_GPU_LOG_OFFSET
 if(ODIN_GPU_LOG_OFFSET+65536>highest)highest=ODIN_GPU_LOG_OFFSET+65536;
 if(ODIN_GPU_LOG_USED_OFFSET+4>highest)highest=ODIN_GPU_LOG_USED_OFFSET+4;
#endif

#ifdef ODIN_UI_THREADS_OFFSET
 if(ODIN_UI_THREADS_OFFSET+2050*8>highest)highest=ODIN_UI_THREADS_OFFSET+2050*8;
#endif
#ifdef ODIN_UI_POLICY_OFFSET
 if(ODIN_UI_POLICY_OFFSET+64>highest)highest=ODIN_UI_POLICY_OFFSET+64;
 if(ODIN_UI_POLICY_COMMAND_OFFSET+4>highest)highest=ODIN_UI_POLICY_COMMAND_OFFSET+4;
#endif
 UINT64 length=highest+4096;UINT8 *mem=calloc(1,length);assert(mem);
 assert(!KernelRange(0,1));context.Memory=(UINT64)(UINTN)mem;context.Length=length;context.VirtualBase=ODIN_KERNEL_BASE;
 mResidentContext=&context;context.Midr=0x411fd440;
 assert(KernelRange(0,length)==mem && !KernelRange(length,1) && !KernelRange(MAX_UINT64,1));
 context.VirtualBase++;assert(!KernelRange(0,1));context.VirtualBase--;
 put64(mem,ODIN_STAGE_OFFSET,0x2f);assert(KernelWord(ODIN_STAGE_OFFSET,8)==0x2f);
 assert(!KernelStage() && !strcmp(lastText,"stage=2f midr=411fd440"));
 assert(!KernelLog() && !strcmp(lastCode,"FAIL"));
 const char sample[]="real kernel log\nnext\001line";memcpy(mem+128,sample,sizeof(sample)-1);
 put64(mem,ODIN_LOG_BASE_OFFSET,ODIN_KERNEL_BASE+128);put64(mem,ODIN_LOG_PTR_OFFSET,ODIN_KERNEL_BASE+128+sizeof(sample)-1);
 UINT32 size=4096;memcpy(mem+ODIN_LOG_SIZE_OFFSET,&size,4);
 assert(!KernelLog() && !strcmp(lastCode,"OKAY") && !memcmp(logText,"real kernel log\nnext.line",sizeof(sample)-1));
 put64(mem,ODIN_LOG_PTR_OFFSET,ODIN_KERNEL_BASE+length+1);assert(!KernelLog() && !strcmp(lastCode,"FAIL"));
 put64(mem,ODIN_LOG_PTR_OFFSET,ODIN_KERNEL_BASE+128+sizeof(sample)-1);
 put64(mem,ODIN_LOG_BASE_OFFSET,ODIN_KERNEL_BASE-1);assert(!KernelLog() && !strcmp(lastCode,"FAIL"));
 UINT8 pixels[24];for(UINTN i=0;i<sizeof(pixels);i++)pixels[i]=(UINT8)i;
 services.LocateProtocol=Locate;gop.Mode=&mode;mode.Info=&info;mode.FrameBufferBase=(UINT64)(UINTN)pixels;mode.FrameBufferSize=sizeof(pixels);
 info.HorizontalResolution=2;info.VerticalResolution=3;info.PixelsPerScanLine=2;info.PixelFormat=PixelBlueGreenRedReserved8BitPerColor;
 CaptureInitialize();assert(mCaptureBytes==24 && mCaptureBase==(UINT64)(UINTN)pixels);
 assert(!CaptureInfo() && !strcmp(lastText,"2:3:8:1:24"));assert(!CaptureUpload() && expectedBytes==24 && wireBytes==24 && !memcmp(wire,pixels,24));
 failTransfer=1;assert(CaptureUpload()==EFI_DEVICE_ERROR);failTransfer=0;
 mCaptureBase=mCaptureBytes=0;mode.FrameBufferSize=23;CaptureInitialize();assert(!mCaptureBytes);assert(!CaptureUpload() && !strcmp(lastCode,"FAIL"));
 mode.FrameBufferSize=24;info.PixelFormat=PixelBitMask;info.PixelInformation.RedMask=0xff0000;info.PixelInformation.GreenMask=0xff00;info.PixelInformation.BlueMask=0xff;
 CaptureInitialize();assert(mCaptureBytes==24 && mCaptureFormat==1);
 mCaptureBase=mCaptureBytes=0;info.PixelInformation.RedMask=0xf800;CaptureInitialize();assert(!mCaptureBytes);
#ifdef ODIN_POSTVM_OFFSET
 put64(mem,ODIN_POSTVM_OFFSET,0x4b);put64(mem,ODIN_POSTCALLER_OFFSET,ODIN_KERNEL_BASE+32);
 assert(!KernelPostStage() && !strncmp(lastText,"stage=4b caller=",16));
#endif
#ifdef ODIN_PANIC_STR_OFFSET
 logBytes=0;assert(!KernelPanic() && !strcmp(lastText,"no published panic format"));
 put64(mem,ODIN_PANIC_STR_OFFSET,ODIN_KERNEL_BASE+256);put64(mem,ODIN_PANIC_CALLER_OFFSET,ODIN_KERNEL_BASE+32);
 memcpy(mem+256,"kernel panic format",20);assert(!KernelPanic() && !strcmp(lastText,"panic format complete"));
#endif
#ifdef ODIN_TOUCH_STATS_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_TOUCH_STATS_OFFSET+i*4,&value,4);}
 assert(!TouchStats() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"touch counters complete"));
 const char expected[]="touch[0]=a0,a1,a2,a3touch[4]=a4,a5,a6,a7touch[8]=a8,a9,aa,abtouch[12]=ac,ad,ae,af";
 assert(logBytes==sizeof(expected)-1 && !memcmp(logText,expected,sizeof(expected)-1));
 UINT64 savedLength=context.Length;context.Length=ODIN_TOUCH_STATS_OFFSET+63;assert(!TouchStats() && !strcmp(lastCode,"FAIL"));context.Length=savedLength;
 mResidentContext=NULL;assert(!TouchStats() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
#ifdef ODIN_HID_STATS_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_HID_STATS_OFFSET+i*4,&value,4);}
 assert(!HidStats() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"hid counters complete"));
 const char expectedHid[]="hid[0]=a0,a1,a2,a3hid[4]=a4,a5,a6,a7hid[8]=a8,a9,aa,abhid[12]=ac,ad,ae,af";
 assert(logBytes==sizeof(expectedHid)-1 && !memcmp(logText,expectedHid,sizeof(expectedHid)-1));
 UINT64 savedHidLength=context.Length;context.Length=ODIN_HID_STATS_OFFSET+63;assert(!HidStats() && !strcmp(lastCode,"FAIL"));context.Length=savedHidLength;
 mResidentContext=NULL;assert(!HidStats() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
#ifdef ODIN_GPU_STATS_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_GPU_STATS_OFFSET+i*4,&value,4);}
 assert(!GpuStats() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"gpu counters complete"));
 const char expectedGpu[]="gpu[0]=a0,a1,a2,a3gpu[4]=a4,a5,a6,a7gpu[8]=a8,a9,aa,abgpu[12]=ac,ad,ae,af";
 assert(logBytes==sizeof(expectedGpu)-1 && !memcmp(logText,expectedGpu,sizeof(expectedGpu)-1));
 UINT64 savedGpuLength=context.Length;context.Length=ODIN_GPU_STATS_OFFSET+63;assert(!GpuStats() && !strcmp(lastCode,"FAIL"));context.Length=savedGpuLength;
 mResidentContext=NULL;assert(!GpuStats() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
#ifdef ODIN_PRESENT_STATS_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_PRESENT_STATS_OFFSET+i*4,&value,4);}
 assert(!PresentStats() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"present counters complete"));
 const char expectedPresent[]="present[0]=a0,a1,a2,a3present[4]=a4,a5,a6,a7present[8]=a8,a9,aa,abpresent[12]=ac,ad,ae,af";
 assert(logBytes==sizeof(expectedPresent)-1 && !memcmp(logText,expectedPresent,sizeof(expectedPresent)-1));
 UINT64 savedPresentLength=context.Length;context.Length=ODIN_PRESENT_STATS_OFFSET+63;assert(!PresentStats() && !strcmp(lastCode,"FAIL"));context.Length=savedPresentLength;
 mResidentContext=NULL;assert(!PresentStats() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
#ifdef ODIN_SURFACE_STATS_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_SURFACE_STATS_OFFSET+i*4,&value,4);}
 assert(!SurfaceStats() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"surface counters complete"));
 const char expectedSurface[]="surface[0]=a0,a1,a2,a3surface[4]=a4,a5,a6,a7surface[8]=a8,a9,aa,absurface[12]=ac,ad,ae,af";
 assert(logBytes==sizeof(expectedSurface)-1 && !memcmp(logText,expectedSurface,sizeof(expectedSurface)-1));
 UINT64 savedSurfaceLength=context.Length;context.Length=ODIN_SURFACE_STATS_OFFSET+63;assert(!SurfaceStats() && !strcmp(lastCode,"FAIL"));context.Length=savedSurfaceLength;
 mResidentContext=NULL;assert(!SurfaceStats() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
#ifdef ODIN_GPU_LOG_OFFSET
 logBytes=0;const char gpuSample[]="actual GPU log\nnext\001line";
 memcpy(mem+ODIN_GPU_LOG_OFFSET,gpuSample,sizeof(gpuSample)-1);
 UINT32 used=sizeof(gpuSample)-1;memcpy(mem+ODIN_GPU_LOG_USED_OFFSET,&used,4);
 assert(!GpuLog() && !strcmp(lastCode,"OKAY") && logBytes==sizeof(gpuSample)-1 && !memcmp(logText,"actual GPU log\nnext.line",sizeof(gpuSample)-1));
 UINT64 gpuSavedLength=context.Length;context.Length=ODIN_GPU_LOG_OFFSET+65535;
 assert(!GpuLog() && !strcmp(lastCode,"FAIL"));context.Length=gpuSavedLength;
 used=65537;memcpy(mem+ODIN_GPU_LOG_USED_OFFSET,&used,4);assert(!GpuLog() && !strcmp(lastCode,"FAIL"));
#endif

#ifdef ODIN_UI_THREADS_OFFSET
 UINT64 u=ODIN_UI_THREADS_OFFSET,b=u+(2+1024)*8;
 assert(!UiThreads() && !strcmp(lastCode,"FAIL"));
 put64(mem,u,0xffffffffffffffffULL);put64(mem,u+8,1);
 put64(mem,b,1);put64(mem,b+8,0xffffffffffffffffULL);put64(mem,b+16,0xffffffffffffffffULL);put64(mem,b+24,96);
 for(unsigned i=0;i<96*9;i++)put64(mem,b+64+i*8,0xffffffffffffffffULL);
 logBytes=0;assert(!UiThreads() && !strcmp(lastCode,"OKAY") && !strcmp(lastText,"UI threads complete"));
 assert(strstr(logText,"ui sequence=ffffffffffffffff count=96 ticks=ffffffffffffffff"));
 assert(strstr(logText,"ui[95]=ffffffffffffffff,ffffffffffffffff,ffffffffffffffff"));
 assert(strstr(logText,"us[95]=ffffffffffffffff,ffffffffffffffff"));
 UINT64 uiLength=context.Length;context.Length=u+2050*8-1;assert(!UiThreads() && !strcmp(lastCode,"FAIL"));context.Length=uiLength;
 mResidentContext=NULL;assert(!UiThreads() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
 put64(mem,b+24,97);assert(!UiThreads() && !strcmp(lastText,"invalid UI sampler row count"));put64(mem,b+24,0);
 put64(mem,u+8,2);assert(!UiThreads() && !strcmp(lastText,"invalid UI sampler bank"));put64(mem,u+8,1);
 put64(mem,b,2);assert(!UiThreads() && !strcmp(lastCode,"FAIL"));put64(mem,b,1);
 put64(mem,b+8,1);assert(!UiThreads() && !strcmp(lastCode,"FAIL"));put64(mem,b+8,0xffffffffffffffffULL);
 logBytes=0;assert(!UiThreads() && !strcmp(lastCode,"OKAY"));
 put64(mem,u+8,0);put64(mem,u+16,1);put64(mem,u+24,0xffffffffffffffffULL);put64(mem,u+40,0);
 logBytes=0;assert(!UiThreads() && !strcmp(lastCode,"OKAY"));
#endif
#ifdef ODIN_UI_POLICY_OFFSET
 logBytes=0;
 for(UINT32 i=0;i<16;i++){UINT32 value=0xa0+i;memcpy(mem+ODIN_UI_POLICY_OFFSET+i*4,&value,4);}
 assert(!UiPolicy() && !strcmp(lastCode,"OKAY") && strstr(logText,"policy[12]=ac,ad,ae,af"));
 assert(!UiPolicyCommand(1) && !strcmp(lastCode,"OKAY") && KernelWord(ODIN_UI_POLICY_COMMAND_OFFSET,4)==1);
 assert(!UiPolicyCommand(2) && !strcmp(lastCode,"FAIL") && KernelWord(ODIN_UI_POLICY_COMMAND_OFFSET,4)==1);
 assert(!UiPolicyCommand(0) && !strcmp(lastCode,"OKAY") && !KernelWord(ODIN_UI_POLICY_COMMAND_OFFSET,4));
 UINT64 policyLength=context.Length;context.Length=ODIN_UI_POLICY_OFFSET+63;assert(!UiPolicy() && !strcmp(lastCode,"FAIL"));
 context.Length=ODIN_UI_POLICY_COMMAND_OFFSET+3;assert(!UiPolicyCommand(1) && !strcmp(lastCode,"FAIL"));context.Length=policyLength;
 mResidentContext=NULL;assert(!UiPolicyCommand(1) && !strcmp(lastCode,"FAIL"));assert(!UiPolicy() && !strcmp(lastCode,"FAIL"));mResidentContext=&context;
#endif
 free(mem);puts("Kernel range bounds, live symbols, touch counters, bounded logs, GOP formats, capture bytes and transfer failures passed");return 0;
}
'''
(OUT/'check.c').write_text(source)
BIN=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin';MU=ROOT/'work/Mu-Silicium-odin'
cmd=[str(BIN/'clang.exe'),'-O1','-fshort-wchar','-D_EFI_X64_','-I',str(OUT.parent),
 '-I',str(MU/'Mu_Basecore/MdePkg/Include'),'-I',str(MU/'Mu_Basecore/MdePkg/Include/X64'),
 str(OUT/'check.c'),'-o',str(OUT/'check.exe')]
r=subprocess.run(cmd,capture_output=True,text=True);assert not r.returncode,r.stdout+r.stderr
r=subprocess.run([str(OUT/'check.exe')],capture_output=True,text=True);assert not r.returncode,r.stdout+r.stderr
report=dict(passed=True,physical_device_tested=False,command=cmd,result=r.stdout.strip(),
 production_header_sha256=hashlib.sha256((OUT.parent/'OdinKernelReadback.h').read_bytes()).hexdigest())
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
