// SPDX-License-Identifier: GPL-2.0-only
// MIX4 ST SALIXP bus parameters from the working r59/r60 source.
// Original iOS16 IOHIDDevice dispatch is independently bound by the build.
#include "OriginalHidDeviceABI.h"
#include "OdinStHidBridge.h"
#include "odin_st_controller_adapter.h"
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOCatalogue.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSKext.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>

extern "C" vm_offset_t ml_io_map(vm_offset_t,vm_size_t);
extern "C" kern_return_t thread_terminate(thread_t);
extern kmod_info_t g_kernel_kmod_info;
extern "C" { volatile uint32_t odin_touch_stats[16]; }
extern "C" { volatile uint32_t odin_hid_stats[16]; }
#include "OdinTouchEdge16.h"
// stage, chip, poll, batches, down, move, up, active, malformed, bus failures,
// accepted reports, rejected reports, last IOReturn, running, sync stage, status.
#define FINGER \
  0x09,0x22,0xa1,0x02,0x09,0x42,0x15,0,0x25,1,0x75,1,0x95,1,0x81,2, \
  0x09,0x47,0x81,2,0x75,6,0x95,1,0x81,3,0x09,0x51,0x75,8,0x95,1, \
  0x15,0,0x26,0xff,0,0x81,2,0x05,1,0x09,0x30,0x15,0,0x26,0xff,0x7f, \
  0x75,16,0x95,1,0x81,2,0x09,0x31,0x81,2,0x05,0x0d,0xc0,
static const uint8_t descriptor[]={0x05,0x0d,0x09,4,0xa1,1,0x85,3,
 FINGER FINGER FINGER FINGER FINGER FINGER FINGER FINGER FINGER FINGER
 0x09,0x54,0x75,8,0x95,1,0x15,0,0x26,0xff,0,0x81,2,0xc0};
#undef FINGER

class OdinStTouch : public IOHIDDevice {
 OSDeclareDefaultStructors(OdinStTouch)
 IOWorkLoop *loop=nullptr;
 IOBufferMemoryDescriptor *report=nullptr;
 struct odin_hid_bridge bridge={};
 vm_offset_t pins=0;
 uint32_t cfg[5]={},io[5]={};
 bool acquired=false,stopping=false,running=false,synchronizing=false;
 bool isStopping()const{return __atomic_load_n(&stopping,__ATOMIC_ACQUIRE);}
 void setRunning(bool value){__atomic_store_n(&running,value,__ATOMIC_RELEASE);}
 uint64_t syncDeadline=0;
 static constexpr unsigned owned[5]={48,49,50,51,23};
 uint32_t read(unsigned pin,unsigned offset=0)const {
  return *reinterpret_cast<volatile uint32_t *>(pins+pin*0x1000+offset);
 }
 void write(unsigned pin,unsigned offset,uint32_t v) {
  *reinterpret_cast<volatile uint32_t *>(pins+pin*0x1000+offset)=v;
  __asm__ volatile("dsb sy":::"memory");
 }
 bool level(unsigned pin)const{return (read(pin,4)&1)!=0;}
 void set(unsigned pin,bool high){write(pin,4,high?2:0);}
 void config(unsigned pin,bool output,unsigned ma) {
  write(pin,0,(read(pin)&~0x3ffu)|((ma/2-1)<<6)|(output?1u<<9:0));
 }
 static void waitUs(unsigned us) {
  if(us<=10) {
   uint64_t deadline;clock_interval_to_deadline(us,NSEC_PER_USEC,&deadline);
   while(mach_absolute_time()<deadline)__asm__ volatile("":::"memory");
  } else delay_for_interval(us,NSEC_PER_USEC);
 }
 bool takePins() {
  if(!level(22)||!level(132))return false;
  for(unsigned n=0;n<5;n++){cfg[n]=read(owned[n]);io[n]=read(owned[n],4);}
  acquired=true;set(51,true);config(51,true,6);set(50,false);config(50,true,6);
  set(49,false);config(49,true,6);config(48,false,6);config(23,false,8);return true;
 }
 void restore() {
  if(!acquired)return;
  set(51,true);set(50,false);
  for(unsigned n=0;n<5;n++) {
   bool output=(cfg[n]&(15u<<2))==0&&(cfg[n]&(1u<<9));
   if(output){write(owned[n],4,io[n]&2);write(owned[n],0,cfg[n]);}
   else {write(owned[n],0,cfg[n]);write(owned[n],4,io[n]&2);}
  }
  acquired=false;
 }
 uint8_t exchange(uint8_t tx) {
  unsigned rx=0;
  for(unsigned b=0;b<8;b++) {
   set(49,(tx&(0x80u>>b))!=0);waitUs(1);set(50,true);waitUs(1);
   rx=(rx<<1)|(level(48)?1u:0u);set(50,false);
  }
  return uint8_t(rx);
 }
 static bool transfer(void *context,const uint8_t *tx,unsigned nt,uint8_t *rx,unsigned nr) {
  auto self=static_cast<OdinStTouch *>(context);
  if(self->isStopping()||!self->acquired||!tx||!nt||nt>5||nr>257||(nr&&!rx))return false;
  const bool id=nt==5&&tx[0]==0xfb&&tx[1]==0x20&&!tx[2]&&!tx[3]&&tx[4]<=4&&nr==3;
  const bool fifo=nt==1&&tx[0]==0x87&&nr>=9&&(nr-1)%8==0;
  const bool command=self->synchronizing&&nt==3&&!nr&&!tx[1]&&
    ((tx[0]==0xa0&&tx[2]<=1)||(tx[0]==0xa4&&tx[2]==1));
  if(!id&&!fifo&&!command)return false;
  self->set(51,false);waitUs(2);
  for(unsigned i=0;i<nt;i++)self->exchange(tx[i]);
  for(unsigned i=0;i<nr;i++)rx[i]=self->exchange(0);
  waitUs(10);self->set(51,true);waitUs(2);return true;
 }
 static bool send(void *context,const uint8_t *bytes,unsigned n) {
  auto self=static_cast<OdinStTouch *>(context);
  if(n!=ODIN_HID_REPORT_BYTES||!self->report)return false;
  if(self->report->writeBytes(0,bytes,n)!=n)return false;
  IOReturn status=self->handleReport(self->report,0,0);
  odin_hid_stats[5]++;
  if(n>=7){odin_hid_stats[6]=bytes[1];odin_hid_stats[7]=bytes[3]|unsigned(bytes[4])<<8;
   odin_hid_stats[8]=bytes[5]|unsigned(bytes[6])<<8;}
  odin_touch_stats[12]=status;return status==kIOReturnSuccess;
 }
 void inspectMatching(IORegistryEntry *parent,unsigned depth) {
  if(!depth)return;
  OSIterator *it=parent->getChildIterator(gIOServicePlane);if(!it)return;
  while(OSObject *child=it->getNextObject()) {
   auto entry=OSDynamicCast(IORegistryEntry,child);if(!entry)continue;
   odin_hid_stats[4]++;
   if(entry->metaCast("IOHIDInterface"))odin_hid_stats[1]++;
   if(entry->metaCast("IOHIDEventDriver")){odin_hid_stats[2]++;odin_edge16::install(entry);}
   if(entry->metaCast("IOHIDEventService"))odin_hid_stats[3]++;
   inspectMatching(entry,depth-1);
  }
  it->release();
 }
 static int syncWait(void *context,unsigned ms) {
  auto self=static_cast<OdinStTouch *>(context);
  if(ms>2||self->isStopping()||mach_absolute_time()>=self->syncDeadline)return 1;
  if(ms)waitUs(ms*1000);
  return self->isStopping()||mach_absolute_time()>=self->syncDeadline;
 }
 static void syncLog(const char *message,uint64_t a,uint64_t b) {
  IOLog("odin touch: %s %llu %llu\n",message,a,b);
 }
 bool synchronize() {
  clock_interval_to_deadline(10000,NSEC_PER_MSEC,&syncDeadline);
  struct odin_st_controller_adapter adapter={};adapter.state=&bridge.core;
  adapter.wait_context=this;adapter.wait=syncWait;
  ODIN_TOUCH_CONTROLLER_IO callbacks={&adapter,odin_st_controller_transfer,odin_st_controller_wait,syncLog};
  ODIN_TOUCH_SYNC_RESULT result={};synchronizing=true;
  int status=OdinTouchControllerSynchronize(&callbacks,&result);synchronizing=false;
  odin_touch_stats[1]=result.ChipId;odin_touch_stats[14]=result.Stage;odin_touch_stats[15]=status;
  bool ready=!status&&!adapter.pending_count&&result.ChipId==0x3640&&result.Stage==ODIN_TOUCH_SYNC_READY;
  odin_st_controller_discard(&adapter);bridge.core.identified=ready;
  bridge.core.scan_restart_needed=false;return ready;
 }
 static void worker(void *context,wait_result_t) {
  auto self=static_cast<OdinStTouch *>(context);
  odin_touch_stats[0]=3;
  unsigned busEnabled=0;PE_parse_boot_argn("odin-touch-bus",&busEnabled,sizeof(busEnabled));
  if(busEnabled!=1){
   for(unsigned n=0;n<500&&!self->isStopping();n++){
    if(n%100==0){for(unsigned i=1;i<=4;i++)odin_hid_stats[i]=0;self->inspectMatching(self,5);}
    IOSleep(10);
   }
   odin_touch_stats[13]=0;self->setRunning(false);self->release();thread_terminate(current_thread());return;
  }
  self->pins=ml_io_map(0x0f100000,0x90000);
  if(self->pins&&!self->isStopping()&&self->takePins()) {
   odin_hid_io callbacks={self,transfer,self,send};odin_hid_init(&self->bridge,callbacks);
   if(self->synchronize()) {
    odin_touch_stats[0]=4;unsigned errors=0;
    for(unsigned tick=0;!self->isStopping();tick++) {
     if(tick%256==0){for(unsigned i=1;i<=4;i++)odin_hid_stats[i]=0;self->inspectMatching(self,5);}
     // HakiOS 2.3.4: read every active poll; idle fallback 16ms, not 80ms.
     if(self->bridge.core.active||!self->level(23)||tick%4==0||self->bridge.queued) {
      int result=odin_hid_poll(&self->bridge);odin_touch_stats[2]++;
      if(result==ODIN_HID_SCAN_RESTART) {if(!self->synchronize())break;}
      else if(result<0) {if(++errors>=4)break;}else errors=0;
      if(self->bridge.core.faulted)break;
      const auto &s=self->bridge.core;
      odin_touch_stats[3]=s.reports;odin_touch_stats[4]=s.down;odin_touch_stats[5]=s.move;
      odin_touch_stats[6]=s.up;odin_touch_stats[7]=s.active;odin_touch_stats[8]=s.malformed;
      odin_touch_stats[9]=s.failures;odin_touch_stats[10]=self->bridge.accepted_reports;
      odin_touch_stats[11]=self->bridge.failed_sends;
     }
     waitUs(4000);
    }
    odin_hid_release(&self->bridge);
   }
   self->restore();
  }
  odin_touch_stats[13]=0;self->setRunning(false);self->release();
  thread_terminate(current_thread());
 }
public:
 IOWorkLoop *getWorkLoop() const override{return loop;}
 OSString *newTransportString()const override{return OSString::withCString("SPI");}
 OSString *newProductString()const override{return OSString::withCString("MIX4 ST SALIXP Touch Screen");}
 IOReturn newReportDescriptor(IOMemoryDescriptor **out)const override {
  if(!out)return kIOReturnBadArgument;
  *out=IOBufferMemoryDescriptor::withBytes(descriptor,sizeof(descriptor),kIODirectionNone);
  return *out?kIOReturnSuccess:kIOReturnNoMemory;
 }
 bool start(IOService *provider)override {
  loop=IOWorkLoop::workLoop();report=IOBufferMemoryDescriptor::withCapacity(ODIN_HID_REPORT_BYTES,kIODirectionNone);
  if(!loop||!report)return false;
  setProperty("Built-In",true);setProperty("DisplayIntegrated",true);
  setProperty("DigitizerCollectionDispatch",true);setProperty("HIDDefaultBehavior",true);
  if(!IOHIDDevice::start(provider))return false;
  registerService();retain();setRunning(true);odin_touch_stats[0]=2;odin_touch_stats[13]=1;
  thread_t thread=THREAD_NULL;kern_return_t status=kernel_thread_start(worker,this,&thread);
  if(status!=KERN_SUCCESS) {setRunning(false);release();odin_touch_stats[13]=0;IOHIDDevice::stop(provider);return false;}
  thread_deallocate(thread);return true;
 }
 void stop(IOService *provider)override {
  __atomic_store_n(&stopping,true,__ATOMIC_RELEASE);
  while(__atomic_load_n(&running,__ATOMIC_ACQUIRE))IOSleep(4);
  IOHIDDevice::stop(provider);
 }
 void free()override {OSSafeReleaseNULL(report);OSSafeReleaseNULL(loop);IOHIDDevice::free();}
};
constexpr unsigned OdinStTouch::owned[5];
OSDefineMetaClassAndStructors(OdinStTouch,IOHIDDevice)

extern "C" void odin_touch_static_init(void) __asm__("__GLOBAL__sub_I_OdinStTouch.cpp");
static bool installDigitizerPersonality() {
 auto personality=OSDictionary::withCapacity(8);
 auto properties=OSDictionary::withCapacity(1);
 auto usage=OSDictionary::withCapacity(2);
 auto pairs=OSArray::withCapacity(1);
 auto drivers=OSArray::withCapacity(1);
 bool okay=personality&&properties&&usage&&pairs&&drivers;
 auto putString=[](OSDictionary *dict,const char *key,const char *text){
  auto value=OSString::withCString(text);bool set=value&&dict->setObject(key,value);OSSafeReleaseNULL(value);return set;
 };
 auto putNumber=[](OSDictionary *dict,const char *key,unsigned number){
  auto value=OSNumber::withNumber(number,32);bool set=value&&dict->setObject(key,value);OSSafeReleaseNULL(value);return set;
 };
 if(okay)okay=putString(personality,"CFBundleIdentifier","com.apple.iokit.IOHIDFamily")&&
  putString(personality,"IOClass","IOHIDEventDriver")&&putString(personality,"IOProviderClass","IOHIDInterface")&&
  putString(personality,"HIDDefaultBehavior","")&&
  putString(properties,"Product","MIX4 ST SALIXP Touch Screen")&&
  putNumber(usage,"DeviceUsagePage",13)&&putNumber(usage,"DeviceUsage",4)&&
  pairs->setObject(usage)&&personality->setObject("DeviceUsagePairs",pairs)&&
  personality->setObject("IOPropertyMatch",properties)&&drivers->setObject(personality);
 if(okay)okay=gIOCatalogue->addDrivers(drivers,true);
 OSSafeReleaseNULL(drivers);OSSafeReleaseNULL(pairs);OSSafeReleaseNULL(usage);
 OSSafeReleaseNULL(properties);OSSafeReleaseNULL(personality);return okay;
}
extern "C" void odin_touch_owner_start(void) {
 unsigned enabled=0;PE_parse_boot_argn("odin-touch",&enabled,sizeof(enabled));
 if(enabled!=1||odin_touch_stats[0])return;
 odin_touch_stats[0]=1;
 IOReturn status=OSKext::loadKextWithIdentifier("com.apple.iokit.IOHIDFamily",
  true,false,kOSKextExcludeNone,kOSKextExcludeNone,nullptr);
 if(status){odin_touch_stats[15]=status;return;}
 // The convenience load above starts code with matching excluded. This codeless
 // plugin supplies the generic IOHIDInterface -> IOHIDEventDriver personality.
 status=OSKext::loadKextWithIdentifier("com.apple.iokit.IOHIDEventDriver",
  true,false,kOSKextExcludeNone,kOSKextExcludeNone,nullptr);
 odin_hid_stats[0]=status;
 if(status){odin_touch_stats[15]=status;return;}
 odin_hid_stats[9]=installDigitizerPersonality()?1:0;
 if(!odin_hid_stats[9]){odin_touch_stats[15]=kIOReturnNoMemory;return;}
 void *handle=OSMetaClass::preModLoad(g_kernel_kmod_info.name);if(!handle)return;
 odin_touch_static_init();status=OSMetaClass::postModLoad(handle);
 if(status){odin_touch_stats[15]=status;return;}
 IOService *parent=IOService::getResourceService();auto device=new OdinStTouch;
 if(!parent||!device||!device->init()||!device->attach(parent)||!device->start(parent)) {
  IOLog("odin touch: failed to publish original HID device\n");return;
 }
 IOLog("odin touch: original HID published; bounded ST initialization worker started\n");
}
