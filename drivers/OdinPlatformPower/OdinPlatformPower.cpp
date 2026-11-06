// SPDX-License-Identifier: MIT
// Adapted from iamojz's SM8350 haydn package/HaydnPlatformPower.cpp.
// Publish the original ApplePMGRNub for AMFI's AON policy latch only.
// This provides no Snapdragon clock, rail, sleep or CPU power operations.
#include <IOKit/IOService.h>
#include <IOKit/IOPlatformExpert.h>
#include <libkern/c++/OSMetaClass.h>
#include <libkern/c++/OSSymbol.h>
#include <libkern/OSKextLib.h>
#include <libkern/libkern.h>

static IOService *odinPolicyNub;

extern "C" void sheng_pmgr_run(void)
{
    if (odinPolicyNub) return;
    OSReturn loaded = OSKextLoadKextWithIdentifier("com.apple.driver.ApplePMGR");
    if (loaded != kOSReturnSuccess)
        panic("odin-pmgr: original ApplePMGR load failed: %x", loaded);
    const OSSymbol *name = OSSymbol::withCString("ApplePMGRNub");
    if (!name) panic("odin-pmgr: name allocation failed");
    const OSMetaClass *meta = OSMetaClass::getMetaClassWithName(name);
    name->release();
    if (!meta || meta->getClassSize() < 0x90)
        panic("odin-pmgr: original nub class absent or too small");
    OSObject *object = meta->alloc();
    IOService *nub = OSDynamicCast(IOService, object);
    if (!nub || !nub->init()) panic("odin-pmgr: original nub initialization failed");
    // Exact iOS16.5/20F66 original readAon/writeAon load this field.
    // With NULL they return UINT32_MAX / no-op without touching hardware.
    // Keep this guard before publication; never install a fabricated PMGR.
    volatile uintptr_t *aonProvider = reinterpret_cast<volatile uintptr_t *>(
        reinterpret_cast<unsigned char *>(nub) + 0x88);
    if (*aonProvider) panic("odin-pmgr: unexpected AON provider before attach");
    IOPlatformExpert *platform = IOService::getPlatform();
    if (!platform || !nub->attach(platform))
        panic("odin-pmgr: cannot attach policy nub to platform");
    if (*aonProvider) panic("odin-pmgr: unexpected AON provider after attach");
    odinPolicyNub = nub;
    nub->registerService();
    printf("odin-pmgr: original ApplePMGRNub published; AON provider NULL; policy latch only\n");
}
