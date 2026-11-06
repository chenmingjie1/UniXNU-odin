// SPDX-License-Identifier: BSD-2-Clause-Patent
// Computer-only, opt-in original display lifecycle integration.
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IOLib.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSSymbol.h>
#include <mach/kmod.h>
#include <pexpert/pexpert.h>

extern "C" kmod_info_t g_kernel_kmod_info;
extern "C" kern_return_t OSKextLoadKextWithIdentifier(const char *);
extern "C" void odin_display_static_init(void) __asm__("__GLOBAL__sub_I_OdinLegacyGOPDisplay.cpp");
extern "C" IOService *odin_display_allocate(void);
extern "C" void odin_keyevents_start(void);
extern "C" {
volatile uint32_t odin_display_owner_stage;
volatile int32_t odin_display_owner_status;
}
static IOService *activeDisplay;
static IOPlatformDevice *activeNub;

extern "C" void odin_display_owner_start(void) {
    unsigned enabled=0;
    PE_parse_boot_argn("odin-gop-display",&enabled,sizeof(enabled));
    if(enabled!=1 || odin_display_owner_stage)return;
    odin_display_owner_stage=1;
    odin_display_owner_status=OSKextLoadKextWithIdentifier("com.apple.iokit.IOMobileGraphicsFamily");
    IOLog("odin display: original family load %d\n",odin_display_owner_status);
    if(odin_display_owner_status)return;
    const OSSymbol *legacyName=OSSymbol::withCString("IOMobileFramebufferLegacy");
    const OSMetaClass *legacy=legacyName?OSMetaClass::getMetaClassWithName(legacyName):nullptr;
    OSSafeReleaseNULL(legacyName);
    if(!legacy) {
        odin_display_owner_status=-1;return;
    }
    odin_display_owner_stage=2;
    void *handle=OSMetaClass::preModLoad(g_kernel_kmod_info.name);
    if(!handle){odin_display_owner_status=-2;return;}
    odin_display_static_init();
    odin_display_owner_status=OSMetaClass::postModLoad(handle);
    if(odin_display_owner_status)return;
    PE_Video video={};
    if(PE_current_console(&video) || !video.v_baseAddr || !video.v_width || !video.v_height ||
       video.v_depth!=32 || video.v_rotate || video.v_width>16384 || video.v_height>16384 ||
       video.v_rowBytes<video.v_width*4 || video.v_rowBytes>UINT64_MAX/video.v_height) {
        odin_display_owner_status=-3;return;
    }
    odin_display_owner_stage=3;
    IOService *display=odin_display_allocate();
    if(!display){odin_display_owner_status=-4;return;}
    if(!display->metaCast("IOMobileFramebufferLegacy") || !display->metaCast("IOMobileFramebuffer") ||
       !display->metaCast("IOService") || !display->init()) {
        odin_display_owner_status=-5;display->release();return;
    }
    odin_display_owner_stage=4;
    odin_display_owner_status=OSKextLoadKextWithIdentifier("com.apple.iokit.IOSurface");
    OSDictionary *matching=IOService::nameMatching("IOCoreSurfaceRoot");
    IOService *surface=matching?IOService::waitForMatchingService(matching,5000000000ULL):nullptr;
    bool surfaceReady=surface!=nullptr;
    OSSafeReleaseNULL(surface);OSSafeReleaseNULL(matching);
    if(odin_display_owner_status || !surfaceReady) {
        if(!odin_display_owner_status)odin_display_owner_status=-6;
        display->release();return;
    }
    odin_display_owner_stage=5;
    IOPlatformDevice *nub=new IOPlatformDevice;
    IOService *parent=IOService::getResourceService();
    IODeviceMemory *memory=IODeviceMemory::withRange(video.v_baseAddr,video.v_rowBytes*video.v_height);
    OSArray *ranges=OSArray::withCapacity(1);
    IORegistryEntry *tree=IORegistryEntry::fromPath("/arm-io",gIODTPlane);
    const char type[]="display-subsystem";
    OSData *typeData=OSData::withBytes(type,sizeof(type));
    bool nubAttached=false,nubStarted=false,treeAttached=false,attached=false,started=false;
    if(nub && parent && memory && ranges && tree && typeData && nub->init() && ranges->setObject(memory)) {
        nub->setDeviceMemory(ranges);nub->setName("OdinGOPFramebuffer");
        nubAttached=nub->attach(parent);
        if(nubAttached)nubStarted=nub->start(parent);
        if(nubStarted && nub->setProperty("device_type",typeData)) {
            nub->setName("gop-display",gIODTPlane);
            treeAttached=nub->attachToParent(tree,gIODTPlane);
        }
        SInt32 score=0;
        odin_display_owner_stage=6;
        if(treeAttached && display->probe(nub,&score)==display)attached=display->attach(nub);
        if(attached) {
            odin_display_owner_stage=7;
            IOLog("odin display: original start enter, %ux%u stride %u\n",
                  unsigned(video.v_width),unsigned(video.v_height),unsigned(video.v_rowBytes));
            started=display->start(nub);
            IOLog("odin display: original start returned %d\n",started);
        }
    }
    if(started) {
        // Original start owns normal publication; no fake display list or success event.
        activeDisplay=display;activeNub=nub;
        odin_display_owner_stage=8;odin_display_owner_status=0;
        unsigned ready=0;PE_parse_boot_argn("odin-gop-ready",&ready,sizeof(ready));
        if(ready==1) {
            extern bool odin_display_activate_mapped(IOService *) __asm__("_odin_display_activate_mapped");
            const bool activated=odin_display_activate_mapped(display);
            IOLog("odin display: mapped scanout readiness %d\n",activated);
        }
    } else {
        odin_display_owner_status=-7;
        if(attached)display->detach(nub);
        if(treeAttached)nub->detachFromParent(tree,gIODTPlane);
        if(nubStarted)nub->stop(parent);
        if(nubAttached)nub->detach(parent);
        OSSafeReleaseNULL(nub);display->release();
    }
    OSSafeReleaseNULL(typeData);OSSafeReleaseNULL(tree);
    OSSafeReleaseNULL(ranges);OSSafeReleaseNULL(memory);
    IOLog("odin display: owner stage %u status %d; presentation unqualified\n",
          odin_display_owner_stage,odin_display_owner_status);
    odin_keyevents_start();
}
