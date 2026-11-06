// SPDX-License-Identifier: GPL-2.0-only
// Edge metadata design reference: OddlyLabs/unixnu-fuxi NativeHidInput.cpp,
// 78f30b651c0ca6ea325682832bb25767523212f5 (BSD-2-Clause-Patent).
// All table sizes, slots and the children offset below were separately checked
// in the original iOS16.5/20F66 IOHIDFamily. No iPadOS17/arm64e table is copied.
#pragma once
#include "OdinTouchEdgePolicy.h"
#if defined(__arm64e__)
#error "The measured edge ABI is arm64 iOS16.5/20F66 only"
#endif

extern "C" const uintptr_t odin_edge_driver_table[];
extern "C" const uintptr_t odin_edge_event_table[];

namespace odin_edge16 {
enum {kDriverSlots=219,kDispatch=198,kGetType=18,kGetInteger=23,kSetInteger=24,kGetFixed=25};
enum : uint32_t {kDigitizer=11,kX=0xb0000,kY=0xb0001,kIndex=0xb0005,
 kMask=0xb0007,kTouch=0xb0009,kFromEdgeTip=0x800};
// A single static table belongs only to the digitizer below this board's own
// HID device. It has kernel lifetime, including any outstanding dispatch.
static uintptr_t copy[kDriverSlots];
static IORegistryEntry *owner=nullptr;
static odin_touch_edge_policy policy={};

template<typename R,typename... A> static R call(void *event,unsigned slot,A... args) {
 return reinterpret_cast<R (*)(void *,A...)>((*reinterpret_cast<const uintptr_t **>(event))[slot])(event,args...);
}
static bool exactEvent(OSObject *event) {
 return event&&*reinterpret_cast<const uintptr_t **>(event)==odin_edge_event_table;
}
static bool mark(OSObject *event) {
 if(!exactEvent(event)) {odin_hid_stats[15]++;return false;}
 if(call<uint32_t>(event,kGetType)!=kDigitizer)return false;
 uint32_t id=call<int32_t,uint32_t,IOOptionBits>(event,kGetInteger,kIndex,0);
 if(id>=256){odin_hid_stats[15]++;return false;}
 uint32_t mask=call<int32_t,uint32_t,IOOptionBits>(event,kGetInteger,kMask,0);
 bool touching=call<int32_t,uint32_t,IOOptionBits>(event,kGetInteger,kTouch,0)!=0;
 int32_t x=call<int32_t,uint32_t,IOOptionBits>(event,kGetFixed,kX,0);
 int32_t y=call<int32_t,uint32_t,IOOptionBits>(event,kGetFixed,kY,0);
 bool began=false,edge=odin_touch_edge_update(&policy,id,touching,x,y,&began);
 if(began){odin_hid_stats[11]++;if(edge)odin_hid_stats[12]++;}
 if(edge){
  call<void,uint32_t,int32_t,IOOptionBits>(event,kSetInteger,kMask,int32_t(mask|kFromEdgeTip),0);
  odin_hid_stats[13]++;
 }
 return edge;
}
static void dispatch(IOService *self,OSObject *event,IOOptionBits options) {
 if(exactEvent(event)&&call<uint32_t>(event,kGetType)==kDigitizer) {
  // appendChild in this exact family loads/stores _children at object+0x18.
  OSArray *children=*reinterpret_cast<OSArray **>(reinterpret_cast<uint8_t *>(event)+24);
  if(children&&OSDynamicCast(OSArray,children)&&children->getCount()<=32) {
   bool edge=false;
   for(unsigned i=0;i<children->getCount();i++)edge|=mark(children->getObject(i));
   if(edge){
    uint32_t mask=call<int32_t,uint32_t,IOOptionBits>(event,kGetInteger,kMask,0);
    call<void,uint32_t,int32_t,IOOptionBits>(event,kSetInteger,kMask,int32_t(mask|kFromEdgeTip),0);
   }
  } else if(!children)mark(event);
  else odin_hid_stats[15]++;
 }
 odin_hid_stats[14]++;
 reinterpret_cast<void (*)(IOService *,OSObject *,IOOptionBits)>(odin_edge_driver_table[kDispatch])(self,event,options);
}
static void install(IORegistryEntry *driver) {
 if(owner||!driver)return;
 unsigned enabled=0;PE_parse_boot_argn("odin-touch-edge",&enabled,sizeof(enabled));
 if(enabled!=1)return;
 auto address=reinterpret_cast<uintptr_t **>(driver);
 // Reject any subclass, any other OS table and already-wrapped instances.
 if(*address!=odin_edge_driver_table){odin_hid_stats[10]=2;return;}
 memcpy(copy,odin_edge_driver_table,sizeof(copy));copy[kDispatch]=reinterpret_cast<uintptr_t>(&dispatch);
 owner=driver;
 __atomic_store_n(address,copy,__ATOMIC_RELEASE);
 odin_hid_stats[10]=1;
 IOLog("odin touch: exact iOS16 edge-contact dispatch enabled\n");
}
}
