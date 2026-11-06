// SPDX-License-Identifier: BSD-2-Clause-Patent
// Computer-only ephemeral state provider adapted from UniXNU/AppleKeyStoreState
// 42ff83e08b2265fe741d4adaf084bebe003452ba. No keys or encrypted storage.
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOLib.h>
#include <libkern/c++/OSSymbol.h>
#include <mach/kmod.h>
#include <pexpert/pexpert.h>

extern "C" {
volatile uint32_t odin_aks_calls[128];
volatile uint32_t odin_aks_opened;
}
// The original iOS16.5 framework uses selectors 0/7/14/17/35. State describes
// this RAM-only fixture: no passcode, no bag, and no locked protected data.
// State bits follow HakiOS MiniAppleKeyStore.cpp at
// 88513176b1e96ecf0b764cd62c6f4e6ac71345e3 (MIT, host-input/LICENSE.HakiOS).
// Bit 1 means no passcode; bit 2 means unlocked since boot. Returning only
// bit 2 caused the original lock manager to request a nonexistent passcode.
static constexpr uint8_t ephemeralStateFlags = 0x6;
static constexpr uint8_t ephemeralLockStateDisabled = 3;
// Never treat these answers as SEP or data-protection support.
static size_t encodeEphemeralState(uint8_t out[128]) {
    struct Entry { const char *key; uint8_t length,value; };
    // Canonical DER SET order: encoded SEQUENCE length, then UTF8 key bytes.
    const Entry entries[]={{"bh",2,0},{"sb",2,0},{"ss",2,ephemeralStateFlags},
        {"sas",3,0},{"sfa",3,0},{"sgs",3,0},{"sls",3,ephemeralLockStateDisabled},{"sms",3,0},
        {"sgpe",4,0},{"srcd",4,0}};
    size_t at=2;
    for(const auto &e:entries) {
        out[at++]=0x30;out[at++]=uint8_t(e.length+5);
        out[at++]=0x0c;out[at++]=e.length;
        for(unsigned i=0;i<e.length;++i)out[at++]=uint8_t(e.key[i]);
        out[at++]=2;out[at++]=1;out[at++]=e.value;
    }
    out[0]=0x31;out[1]=uint8_t(at-2);return at;
}
class AppleKeyStoreUserClient final : public IOUserClient {
    OSDeclareDefaultStructors(AppleKeyStoreUserClient)
public:
    IOReturn clientClose() override { terminate();return kIOReturnSuccess; }
    IOReturn externalMethod(uint32_t selector,IOExternalMethodArguments *args,
                           IOExternalMethodDispatch *,OSObject *,void *) override {
        IOReturn result=kIOReturnUnsupported;
        if(!args)return kIOReturnBadArgument;
        const bool noInputStructure=!args->structureInputSize && !args->structureInputDescriptor;
        const bool noOutputStructure=!args->structureOutputSize && !args->structureOutputDescriptor;
        switch(selector) {
        case 0: // Actual zero-argument connection handshake, not an unlock.
            result=(!args->scalarInputCount && !args->scalarOutputCount &&
                noInputStructure && noOutputStructure)?kIOReturnSuccess:kIOReturnBadArgument;
            break;
        case 7: // aks_get_lock_state: one bag scalar, one output scalar.
        case 14: // aks_get_system: zero or one input, one handle output.
            if(noInputStructure && noOutputStructure && args->scalarOutputCount==1 && args->scalarOutput &&
               ((selector==7 && args->scalarInputCount==1 && args->scalarInput) ||
                (selector==14 && args->scalarInputCount<=1 && (!args->scalarInputCount || args->scalarInput)))) {
                // Handle zero is the ephemeral system context, not a loaded keybag.
                args->scalarOutput[0]=selector==7?ephemeralStateFlags:0;result=kIOReturnSuccess;
            } else result=kIOReturnBadArgument;
            break;
        case 17: case 35: {
            if(!noInputStructure || args->scalarInputCount!=1 || !args->scalarInput || args->scalarOutputCount) {
                result=kIOReturnBadArgument;break;
            }
            uint8_t der[128]={};const size_t n=encodeEphemeralState(der);
            if(args->structureOutputDescriptor) {
                auto memory=args->structureOutputDescriptor;
                if(n>memory->getLength() || n>args->structureOutputDescriptorSize)result=kIOReturnNoSpace;
                else if(memory->writeBytes(0,der,n)!=n)result=kIOReturnError;
                else {args->structureOutputDescriptorSize=n;result=kIOReturnSuccess;}
            } else if(args->structureOutput && n<=args->structureOutputSize) {
                memcpy(args->structureOutput,der,n);args->structureOutputSize=uint32_t(n);result=kIOReturnSuccess;
            } else result=kIOReturnNoSpace;
            break;
        }
        default: break; // Key operations, keybag mutation and unqualified calls fail.
        }
        const uint32_t calls=selector<128?__sync_fetch_and_add(&odin_aks_calls[selector],1):0;
        if(calls<2)IOLog("odin aks: selector %u in %u out %u struct %u result %d\n",
            selector,args->scalarInputCount,args->scalarOutputCount,args->structureOutputSize,result);
        return result;
    }
};
OSDefineMetaClassAndStructors(AppleKeyStoreUserClient,IOUserClient)

class AppleKeyStore final : public IOService {
    OSDeclareDefaultStructors(AppleKeyStore)
    IOReturn openState(task_t task,void *security,UInt32 type,OSDictionary *properties,IOUserClient **out) {
        if(out)*out=nullptr;
        unsigned enabled=0;PE_parse_boot_argn("odin-key-state",&enabled,sizeof(enabled));
        if(enabled!=1)return kIOReturnUnsupported;
        if(!out || type)return kIOReturnBadArgument;
        auto client=new AppleKeyStoreUserClient;
        if(!client)return kIOReturnNoMemory;
        if(!client->initWithTask(task,security,type,properties)) { client->release();return kIOReturnError; }
        if(!client->attach(this)) { client->release();return kIOReturnError; }
        if(!client->start(this)) { client->detach(this);client->release();return kIOReturnError; }
        __sync_fetch_and_add(&odin_aks_opened,1);*out=client;return kIOReturnSuccess;
    }
public:
    bool start(IOService *provider) override {
        if(!IOService::start(provider))return false;
        setName("Odin offline keystore notification service");
        if(!setProperty("NativeKeyStoreEvents",true) ||
           !setProperty("KeyOperationsAvailable",false)) {
            IOService::stop(provider);return false;
        }
        registerService();
        return true;
    }
    IOReturn newUserClient(task_t t,void *s,UInt32 type,OSDictionary *p,IOUserClient **out) override {
        return openState(t,s,type,p,out);
    }
    IOReturn newUserClient(task_t t,void *s,UInt32 type,IOUserClient **out) override {
        return newUserClient(t,s,type,nullptr,out);
    }
};
OSDefineMetaClassAndStructors(AppleKeyStore,IOService)
extern "C" void odin_keyevents_static_init(void) __asm__("__GLOBAL__sub_I_OdinKeyStoreEvents.cpp");
extern "C" kmod_info_t g_kernel_kmod_info;
extern "C" {
volatile uint32_t odin_keyevents_stage;
}
static AppleKeyStore *activeKeyEvents;
extern "C" void odin_keyevents_start(void) {
    unsigned enabled=0;PE_parse_boot_argn("odin-key-events",&enabled,sizeof(enabled));
    if(enabled!=1 || odin_keyevents_stage)return;
    odin_keyevents_stage=1;
    // The pinned original iOS16 kernel has no AppleKeyStore class. Refuse a
    // conflicting provider rather than registering a second metaclass.
    const OSSymbol *name=OSSymbol::withCString("AppleKeyStore");
    if(!name)return;
    const bool exists=OSMetaClass::getMetaClassWithName(name)!=nullptr;
    name->release();
    if(exists) {
        IOLog("odin keyevents: existing AppleKeyStore class; registration refused\n");return;
    }
    // Constructors initially hold C-string class names. postModLoad interns
    // them as OSSymbols and registers the class before registry RPCs use it.
    void *handle=OSMetaClass::preModLoad(g_kernel_kmod_info.name);
    if(!handle) { IOLog("odin keyevents: preModLoad failed\n");return; }
    odin_keyevents_static_init();
    const OSReturn registration=OSMetaClass::postModLoad(handle);
    if(registration!=kOSReturnSuccess) {
        IOLog("odin keyevents: postModLoad failed %d\n",registration);return;
    }
    odin_keyevents_stage=2;
    IOService *parent=IOService::getPlatform();
    AppleKeyStore *service=new AppleKeyStore;
    bool attached=false;
    if(service && parent && service->init())attached=service->attach(parent);
    if(attached && service->start(parent)) {
        activeKeyEvents=service;odin_keyevents_stage=3;
        IOLog("odin keyevents: original matching class published; state/key operations unsupported\n");
    } else {
        if(attached)service->detach(parent);
        OSSafeReleaseNULL(service);
        IOLog("odin keyevents: service start failed\n");
    }
}
