// SPDX-License-Identifier: APSL-2.0
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <libkern/c++/OSKext.h>
#include <kern/thread.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include "OdinAdrenoApi.h"
extern kmod_info_t g_kernel_kmod_info;
extern "C" kern_return_t thread_terminate(thread_t);
extern "C" void odin_adreno_static_init(void) __asm__("__GLOBAL__sub_I_OdinAdrenoService.cpp");
extern "C" {volatile uint32_t odin_gpu_stats[16];}
extern "C" {char odin_gpu_log[65536];volatile uint32_t odin_gpu_log_used;}
extern "C" void odin_gpu_log_append(const char *line) {
 uint32_t n=(uint32_t)strnlen(line,400),old=__atomic_load_n(&odin_gpu_log_used,__ATOMIC_RELAXED);
 while(old<sizeof(odin_gpu_log)) {
  uint32_t take=n;if(take>sizeof(odin_gpu_log)-old)take=sizeof(odin_gpu_log)-old;
  if(__atomic_compare_exchange_n(&odin_gpu_log_used,&old,old+take,false,__ATOMIC_RELAXED,__ATOMIC_RELAXED)) {
   memcpy(odin_gpu_log+old,line,take);if(take<n)odin_gpu_stats[9]=1;return;
  }
 }
 odin_gpu_stats[9]=1;
}

extern "C" void redwood_tl(const char *fmt,...) {
 char line[400];va_list args;va_start(args,fmt);vsnprintf(line,sizeof(line),fmt,args);va_end(args);odin_gpu_log_append(line);IOLog("%s",line);
}
extern "C" void hakios_tl(const char *fmt,...) {
 char line[400];va_list args;va_start(args,fmt);vsnprintf(line,sizeof(line),fmt,args);va_end(args);odin_gpu_log_append(line);IOLog("%s",line);
}
extern "C" void odin_adreno_test_frame(const uint8_t *pixels,uint32_t width,uint32_t height,uint32_t stride) {
 (void)pixels;(void)width;(void)height;(void)stride;
 IOLog("odin GPU: offscreen test does not replace original display scanout\n");
}
static void worker(void *,wait_result_t) {
 odin_gpu_stats[0]=2;
 redwood_adreno_init();
 odin_gpu_stats[2]=redwood_gpu_ready()?1:0;
 if(odin_gpu_stats[2]){uint64_t chip=0;redwood_gpu_parameter(3,&chip);odin_gpu_stats[3]=(uint32_t)chip;}
 unsigned test=0;PE_parse_boot_argn("odin-gpu-selftest",&test,sizeof(test));
 if(odin_gpu_stats[2]&&test==1)odin_gpu_stats[10]=odin_adreno_offscreen_test()?1:2;
 odin_gpu_stats[0]=3;
 thread_terminate(current_thread());
}
extern "C" void odin_gpu_owner_start(void) {
 extern void odin_ui_sampler_start(void) __asm__("_odin_ui_sampler_start");
 odin_ui_sampler_start();
 unsigned enabled=0,probe=0;
 PE_parse_boot_argn("odin-gpu",&enabled,sizeof(enabled));
 PE_parse_boot_argn("adreno",&probe,sizeof(probe));
 if(enabled!=1||probe||odin_gpu_stats[0])return;
 odin_gpu_stats[0]=1;
 void *handle=OSMetaClass::preModLoad(g_kernel_kmod_info.name);if(!handle){odin_gpu_stats[15]=1;return;}
 odin_adreno_static_init();IOReturn status=OSMetaClass::postModLoad(handle);
 if(status){odin_gpu_stats[15]=status;return;}
 thread_t t=THREAD_NULL;kern_return_t result=kernel_thread_start(worker,nullptr,&t);
 if(result!=KERN_SUCCESS){odin_gpu_stats[15]=result;return;}
 thread_deallocate(t);
}
