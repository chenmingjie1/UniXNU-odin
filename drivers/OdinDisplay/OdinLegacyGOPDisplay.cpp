// SPDX-License-Identifier: BSD-2-Clause-Patent
// iOS 16.5 backend entry. Opt-in computer replay only. Original start and
// client access are under validation; surface presentation is incomplete.
#include "OriginalLegacyFramebufferABI.h"
#include "OriginalSurface16.h"
#include "OdinScanoutCopy.h"
#include <kern/clock.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/pwr_mgt/IOPM.h>
#include <IOKit/IOWorkLoop.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <pexpert/pexpert.h>
extern "C" { volatile uint32_t odin_surface_inspections[16]; }
extern "C" {volatile uint32_t odin_present_stats[16];}
static uint32_t presentUs(uint64_t from,uint64_t to) {
 uint64_t ns=0;absolutetime_to_nanoseconds(to-from,&ns);return ns/1000>UINT32_MAX?UINT32_MAX:uint32_t(ns/1000);
}
static void samplePresent(unsigned index,uint32_t value) {
 odin_present_stats[index]=value;if(value>odin_present_stats[index+1])odin_present_stats[index+1]=value;
}


// Compiler evidence for the original IOSurface's source-kernel memory ABI.
// These are never called by the inspector and perform no memory operations.
extern "C" uint64_t odin_memory_length_contract(IOMemoryDescriptor *m) { return m->getLength(); }
extern "C" IOReturn odin_memory_prepare_contract(IOMemoryDescriptor *m) { return m->prepare(); }
extern "C" IOReturn odin_memory_complete_contract(IOMemoryDescriptor *m) { return m->complete(); }

class OdinLegacyGOPDisplay : public IOMobileFramebufferLegacy {
    OSDeclareDefaultStructors(OdinLegacyGOPDisplay)
    IOMemoryMap *mapping=nullptr;
    const void *validatedRequest=nullptr;
    bool logicalPM=false;
    bool kicking=false,rekick=false;
    bool consoleReleased=false;
    IOBufferMemoryDescriptor *scanoutShadow=nullptr;
    bool shadowValid=false;
public:
    bool startLogicalScheduling() {
        unsigned enabled=0;
        PE_parse_boot_argn("odin-gop-pm",&enabled,sizeof(enabled));
        if(!enabled)return true;
        IOService *provider=getProvider();
        if(enabled!=1 || !mapping || !provider)return false;
        if(logicalPM)return true;
        // Adapted from UniXNU/GopFramebuffer e47c1b8, startDisplay(). This is
        // the actual IOKit scheduling lifecycle, not a private-field write.
        // The local iOS16 gate reads +5236 (iPadOS17 uses another layout).
        // Firmware owns physical panel power; advertise logical usability only.
        static IOPMPowerState states[2]={};
        states[0].version=states[1].version=1;
        states[1].capabilityFlags=kIOPMDeviceUsable;
        PMinit();logicalPM=initialized;
        if(!logicalPM)return false;
        provider->joinPMtree(this);
        IOReturn status=registerPowerDriver(this,states,2);
        IOLog("OdinLegacyGOPDisplay: logical PM register status %d schedule %u\n",status,logicalScheduling());
        if(status==kIOReturnSuccess)status=changePowerStateToPriv(1);
        IOLog("OdinLegacyGOPDisplay: logical PM request status %d schedule %u\n",status,logicalScheduling());
        if(status!=kIOReturnSuccess){PMstop();logicalPM=false;return false;}
        return true;
    }
    IOReturn setPowerState(unsigned long ordinal,IOService *device) override {
        if(logicalPM && (ordinal>1 || !mapping))return kIOReturnUnsupported;
        const uint32_t before=logicalScheduling();
        IOReturn status=IOMobileFramebufferLegacy::setPowerState(ordinal,device);
        IOLog("OdinLegacyGOPDisplay: logical PM callback %lu schedule %u -> %u power %u status %d\n",
            ordinal,before,logicalScheduling(),logicalScanoutPower(),status);
        return status;
    }
    bool validateSwap(const void *request) override {
        // Upstream NativeLegacyDisplay validation, requalified against the
        // actual iOS16 request snapshot and original stores. CPU-only host
        // presentation accepts a single full-frame BGRA surface over black.
        unsigned enabled=0;
        PE_parse_boot_argn("odin-surface-inspect",&enabled,sizeof(enabled));
        if(enabled!=1 || !request)return false;
        const uint32_t seen=__sync_fetch_and_add(&odin_surface_inspections[0],1);
        OSObject *surfaces[4]={};
        memcpy(surfaces,reinterpret_cast<const unsigned char *>(request)+2184,sizeof(surfaces));
        for(unsigned layer=0;layer<4;++layer) {
            OSObject *surface=surfaces[layer];
            if(!surface)continue;
            __sync_fetch_and_add(&odin_surface_inspections[1],1);
            if(!surface->metaCast("IOSurface")) {
                __sync_fetch_and_add(&odin_surface_inspections[2],1);continue;
            }
            IOMemoryDescriptor *memory=odin_surface_descriptor(surface);
            const bool backed=memory && memory->metaCast("IOMemoryDescriptor");
            const uint32_t width=odin_surface_width(surface),height=odin_surface_height(surface);
            const uint32_t stride=odin_surface_stride(surface),allocation=odin_surface_allocation(surface);
            const uint32_t format=odin_surface_format(surface),planes=odin_surface_planes(surface);
            const uint64_t length=backed?memory->getLength():0;
            if(backed)__sync_fetch_and_add(&odin_surface_inspections[3],1);
            if(seen<8)IOLog("OdinLegacyGOPDisplay: surface layer %u %ux%u stride %u allocation %u format %x planes %u memory %llu; inspected\n",
                layer,width,height,stride,allocation,format,planes,length);
        }
        unsigned present=0;PE_parse_boot_argn("odin-gop-cpu",&present,sizeof(present));
        if(present!=1 || !logicalPM || !mapping || validatedRequest)return false;
        auto bytes=reinterpret_cast<const unsigned char *>(request);
        auto word=[&](unsigned offset){uint32_t value=0;memcpy(&value,bytes+offset,4);return value;};
        const uint32_t updated=word(792),disabled=word(796),background=word(800),known=0x8000000fU;
        bool state=!((updated|disabled)&~known) && !(disabled&~updated) && (updated&~disabled)==1;
        state=state && ((updated&0x80000000U)?((disabled&0x80000000U) && background==0xff000000U):background==0);
        uint32_t width=0,height=0;getDisplayDimensions(&width,&height);
        bool geometry=word(816)==width && word(820)==height;
        const unsigned rectangles[]={17U,81U};
        for(unsigned offset: rectangles) {
            uint32_t rect[4]={};memcpy(rect,bytes+offset,sizeof(rect));
            geometry=geometry && !rect[0] && !rect[1] && rect[2]==width && rect[3]==height;
        }
        // Conservative refusal of nonzero request options; no transformation,
        // scaling, detached layers or GPU producer completion is implemented.
        for(unsigned offset=804;offset<=812;offset+=4)geometry=geometry && !word(offset);
        for(unsigned offset=824;offset<=840;offset+=4)geometry=geometry && !word(offset);
        OSObject *surface=surfaces[0];
        bool valid=state && geometry && surface && !surfaces[1] && !surfaces[2] && !surfaces[3] && surface->metaCast("IOSurface");
        if(valid) {
            IOMemoryDescriptor *memory=odin_surface_descriptor(surface);
            uint64_t stride=odin_surface_stride(surface),allocation=odin_surface_allocation(surface);
            valid=odin_surface_width(surface)==width && odin_surface_height(surface)==height &&
                odin_surface_format(surface)==0x42475241U && !odin_surface_planes(surface) &&
                stride>=uint64_t(width)*4 && !(stride&3) && height && stride<=UINT64_MAX/height &&
                allocation>=stride*height && memory && memory->metaCast("IOMemoryDescriptor") && memory->getLength()>=allocation;
        }
        if(valid){validatedRequest=request;__sync_fetch_and_add(&odin_surface_inspections[4],1);}
        else if(__sync_fetch_and_add(&odin_surface_inspections[5],1)<8)
            IOLog("OdinLegacyGOPDisplay: reject CPU state %u geometry %u masks %x %x background %x\n",state,geometry,updated,disabled,background);
        return valid;
    }
    void kickSwapQueue() override {
        if(kicking){rekick=true;return;}
        kicking=true;
        do {rekick=false;copyPendingFrame();} while(rekick);
        kicking=false;
    }
    void copyPendingFrame() {
        __sync_fetch_and_add(&odin_surface_inspections[6],1);
        unsigned present=0;PE_parse_boot_argn("odin-gop-cpu",&present,sizeof(present));
        if(present!=1)return;
        const void *request=readySwapRequest();
        if(!mapping || !logicalPM || !request || request!=validatedRequest) {
            if(__sync_fetch_and_add(&odin_surface_inspections[12],1)<8)
                IOLog("OdinLegacyGOPDisplay: CPU kick ready %p validated %p PM %u\n",request,validatedRequest,logicalPM);
            return;
        }
        IOWorkLoop *loop=getWorkLoop();
        if(!loop || !loop->inGate()) {
            if(__sync_fetch_and_add(&odin_surface_inspections[11],1)<8)IOLog("OdinLegacyGOPDisplay: CPU kick outside original workloop gate\n");
            return;
        }
        OSObject *surface=nullptr;memcpy(&surface,reinterpret_cast<const unsigned char *>(request)+2184,8);
        IOMemoryDescriptor *memory=odin_surface_descriptor(surface);
        const uint64_t stride=odin_surface_stride(surface),allocation=odin_surface_allocation(surface);
        PE_Video video={};
        if(PE_current_console(&video) || video.v_baseAddr!=mapping->getPhysicalAddress() ||
           video.v_depth!=32 || video.v_rotate || !video.v_height || video.v_width>16384 ||
           video.v_rowBytes<uint64_t(video.v_width)*4 || video.v_rowBytes>UINT64_MAX/video.v_height ||
           video.v_rowBytes*video.v_height>mapping->getLength())return;
        const uint64_t frameStart=mach_absolute_time();odin_present_stats[0]++;
        IOReturn status=memory->prepare();
        if(status!=kIOReturnSuccess)odin_present_stats[12]++;
        IOMemoryMap *source=status==kIOReturnSuccess?memory->map(kIOMapAnywhere|kIOMapReadOnly|kIOMapCopybackCache):nullptr;
        const uint64_t mapEnd=mach_absolute_time();samplePresent(4,presentUs(frameStart,mapEnd));
        const bool valid=source && source->getVirtualAddress() && source->getLength()>=allocation && mapping->getVirtualAddress();
        if(valid) {
            // Stop the text console repainting the actual system scanout.
            if(!consoleReleased){PE_initialize_console(nullptr,kPEDisableScreen);consoleReleased=true;}
            __asm__ volatile("dsb sy" ::: "memory");
            auto destination=reinterpret_cast<volatile unsigned char *>(mapping->getVirtualAddress());
            auto pixels=reinterpret_cast<const unsigned char *>(source->getVirtualAddress());
            unsigned dirty=0;PE_parse_boot_argn("odin-gop-dirty",&dirty,sizeof(dirty));
            const uint64_t shadowBytes=uint64_t(video.v_width)*4*video.v_height;
            if(dirty==1 && (!scanoutShadow||scanoutShadow->getLength()!=shadowBytes)) {
                OSSafeReleaseNULL(scanoutShadow);shadowValid=false;
                scanoutShadow=IOBufferMemoryDescriptor::withCapacity(shadowBytes,kIODirectionNone);
            }
            auto shadow=dirty==1&&scanoutShadow?reinterpret_cast<uint32_t *>(scanoutShadow->getBytesNoCopy()):nullptr;
            unsigned modes=shadow?4U:0U;uint32_t copiedBytes=0;
            for(uint32_t y=0;y<video.v_height;++y) {
                auto out=reinterpret_cast<volatile uint32_t *>(destination+uint64_t(y)*video.v_rowBytes);
                auto in=reinterpret_cast<const uint32_t *>(pixels+uint64_t(y)*stride);
                if(shadow) {
                    copiedBytes+=4*odin_copy_scanout_cached_row(out,in,shadow+uint64_t(y)*video.v_width,
                        uint32_t(video.v_width),shadowValid);
                    modes|=(((uintptr_t)out|(uintptr_t)in)&7)?1U:2U;
                } else {
                    modes|=1U<<odin_copy_scanout_row(out,in,uint32_t(video.v_width));
                    copiedBytes+=uint32_t(video.v_width)*4;
                }
            }
            __asm__ volatile("dsb sy" ::: "memory");
            shadowValid=shadow!=nullptr;
            if(!copiedBytes)modes|=8U;
            const uint32_t us=presentUs(mapEnd,mach_absolute_time());samplePresent(2,us);
            odin_present_stats[1]++;odin_present_stats[10]=modes;odin_present_stats[11]=copiedBytes;
            if(us>16667)odin_present_stats[14]++;odin_present_stats[15]+=us;
            __sync_fetch_and_add(&odin_surface_inspections[7],1);
        } else {odin_present_stats[13]++;__sync_fetch_and_add(&odin_surface_inspections[9],1);}
        OSSafeReleaseNULL(source);
        if(status==kIOReturnSuccess)memory->complete();
        if(!valid)return;
        if(!activateOnlyReadySwap(request)) {
            if(__sync_fetch_and_add(&odin_surface_inspections[10],1)<8)IOLog("OdinLegacyGOPDisplay: CPU copied, sole pending activation refused\n");
            return;
        }
        validatedRequest=nullptr;
        // Real memory stores precede the unchanged family's release/wakeup.
        // This is software scanout completion, not a panel vblank/GPU fence.
        const uint64_t retireStart=mach_absolute_time();
        IOMobileFramebufferLegacy::completeCurrentSwap();
        samplePresent(6,presentUs(retireStart,mach_absolute_time()));samplePresent(8,presentUs(frameStart,mach_absolute_time()));
        const uint32_t retired=__sync_fetch_and_add(&odin_surface_inspections[8],1)+1;
        if(retired<=8)IOLog("OdinLegacyGOPDisplay: CPU copied and retired frame %u, %ux%u source stride %llu destination %llu\n",
            retired,uint32_t(video.v_width),uint32_t(video.v_height),stride,uint64_t(video.v_rowBytes));
        rekick=true;
    }
    IOReturn collectCompletionReports(uint32_t,void *,uint32_t *count,uint32_t) override {
        if(count)*count=0;
        return kIOReturnUnsupported;
    }
    bool activateMappedScanout() {
        // The exact original state setter, not a guessed private-field store.
        // A mapped firmware framebuffer is ready for logical scanout. This
        // does not assert a physical panel transition or hardware vblank.
        if(!mapping)return false;
        const uint32_t before=logicalScanoutPower();
        const OriginalLegacyStateRequest request={1,0,0,1,1,{0,0,0}};
        const IOReturn status=applyStateRequest(&request,false);
        const uint32_t after=logicalScanoutPower();
        IOLog("OdinLegacyGOPDisplay: mapped scanout power %u -> %u status %d\n",before,after,status);
        return status==kIOReturnSuccess && after==1 && startLogicalScheduling();
    }
    IOReturn queryOutput64(uint32_t selector,uint32_t *value,void *output) override {
        // Original client selector74 enforces one scalar and a 64-byte output.
        // Its platform-specific contents are not implemented by a GOP buffer.
        // Return an honest unsupported result instead of the pure-virtual trap.
        if(!value || !output)return kIOReturnBadArgument;
        *value=0;
        bzero(output,64);
        IOLog("OdinLegacyGOPDisplay: query74 input %u unsupported\n",selector);
        return kIOReturnUnsupported;
    }
    IOReturn getDotPitch(uint32_t *pitch) override {
        // Actual iOS16 slot 188 reads the AppleARMIODevice "dot-pitch".
        // A GOP buffer provides no physical density. Preserve the original
        // missing-property result, without dereferencing that absent device.
        if(!pitch)return kIOReturnBadArgument;
        *pitch=0;
        return kIOReturnNotFound;
    }
    void free() override {
        if(logicalPM){PMstop();logicalPM=false;}
        OSSafeReleaseNULL(mapping);
        OSSafeReleaseNULL(scanoutShadow);shadowValid=false;
        IOMobileFramebufferLegacy::free();
    }
    void stop(IOService *provider) override {
        if(logicalPM){PMstop();logicalPM=false;}
        IOMobileFramebufferLegacy::stop(provider);
        OSSafeReleaseNULL(mapping);
        OSSafeReleaseNULL(scanoutShadow);shadowValid=false;
    }
    bool startHardware() override {
        unsigned enabled=0;
        PE_parse_boot_argn("odin-gop-display",&enabled,sizeof(enabled));
        if(enabled!=1 || mapping)return false;
        PE_Video video={};
        IOService *provider=getProvider();
        if(!provider || PE_current_console(&video) || !video.v_baseAddr ||
           !video.v_width || !video.v_height || video.v_depth!=32 || video.v_rotate ||
           video.v_width>16384 || video.v_height>16384 ||
           video.v_rowBytes<video.v_width*4 || video.v_rowBytes>UINT64_MAX/video.v_height)
            return false;
        IOMemoryMap *candidate=provider->mapDeviceMemoryWithIndex(0,kIOMapInhibitCache);
        if(!candidate)return false;
        const uint64_t length=video.v_rowBytes*video.v_height;
        bool valid=candidate->getVirtualAddress() &&
            candidate->getPhysicalAddress()==video.v_baseAddr && candidate->getLength()==length;
        if(valid) {
            installBootDimensions(uint32_t(video.v_width),uint32_t(video.v_height));
            uint32_t width=0,height=0;
            getDisplayDimensions(&width,&height);
            valid=width==video.v_width && height==video.v_height;
        }
        if(!valid) {
            candidate->release();
            return false;
        }
        mapping=candidate;
        unsigned present=0;PE_parse_boot_argn("odin-gop-cpu",&present,sizeof(present));
        if(present==1) {
            OSDictionary *layers=OSDictionary::withCapacity(1);
            OSNumber *count=OSNumber::withNumber(1ULL,32);
            bool published=layers && count && layers->setObject("MaxNumLayers",count) && setProperty("IOMFBNumLayers",layers);
            OSSafeReleaseNULL(count);OSSafeReleaseNULL(layers);
            if(!published){OSSafeReleaseNULL(mapping);return false;}
        }
        IOLog("OdinLegacyGOPDisplay: mapped %ux%u, %llu bytes; presentation not implemented\n",
            uint32_t(video.v_width),uint32_t(video.v_height),length);
        return true;
    }
#define ODIN_UNCLASSIFIED(n) \
    __attribute__((noreturn,noinline)) void unclassified##n() override { \
        panic("OdinLegacyGOPDisplay: unqualified iOS16 slot %u caller %p",n,__builtin_return_address(0)); \
    }
    ODIN_UNCLASSIFIED(211)
    ODIN_UNCLASSIFIED(242)
    ODIN_UNCLASSIFIED(243)
    ODIN_UNCLASSIFIED(292)
    ODIN_UNCLASSIFIED(293)
    ODIN_UNCLASSIFIED(322)
    ODIN_UNCLASSIFIED(329)
#undef ODIN_UNCLASSIFIED
};
OSDefineMetaClassAndStructors(OdinLegacyGOPDisplay,IOMobileFramebufferLegacy)
static_assert(sizeof(OdinLegacyGOPDisplay)==0x1688,"Original class plus mapping, request, logical PM and cached scanout shadow");
extern "C" IOService *odin_display_allocate(void) { return new OdinLegacyGOPDisplay; }
extern "C" bool odin_display_activate_mapped(IOService *display) {
    auto backend=OSDynamicCast(OdinLegacyGOPDisplay,display);
    return backend && backend->activateMappedScanout();
}
