/* Host-only iOS16.5 virtual HID test. No physical device or kernel ABI hooks.
 * API declarations and service property protocol adapted from HakiOS
 * userland/src/inject.c, commit 88513176b1e96ecf0b764cd62c6f4e6ac71345e3.
 * Copyright (c) 2025-2026 the HakiOS authors. MIT; see LICENSE.HakiOS.
 */
typedef unsigned char Boolean;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;
typedef long CFIndex;
typedef const void *CFTypeRef;
typedef const void *CFStringRef;
typedef const void *CFDictionaryRef;
typedef void *CFMutableDictionaryRef;
typedef void *CFNumberRef;
typedef void *CFArrayRef;
typedef void *HIDClient;
typedef void *HIDService;
typedef void *HIDEvent;
extern const void *kCFBooleanTrue;
extern const char kCFTypeDictionaryKeyCallBacks[], kCFTypeDictionaryValueCallBacks[], kCFTypeArrayCallBacks[];
extern CFStringRef CFStringCreateWithCString(void *, const char *, uint32_t);
extern Boolean CFStringGetCString(CFStringRef, char *, CFIndex, uint32_t);
extern CFMutableDictionaryRef CFDictionaryCreateMutable(void *, CFIndex, const void *, const void *);
extern void CFDictionarySetValue(CFMutableDictionaryRef, CFTypeRef, CFTypeRef);
extern CFTypeRef CFDictionaryGetValue(CFDictionaryRef, CFTypeRef);
extern CFNumberRef CFNumberCreate(void *, long, const void *);
extern uint64_t CFNumberGetTypeID(void);
extern Boolean CFNumberGetValue(CFNumberRef, long, void *);
extern CFArrayRef CFArrayCreate(void *, const void **, CFIndex, const void *);
extern CFTypeRef CFRetain(CFTypeRef);
extern void CFRelease(CFTypeRef);
extern Boolean CFEqual(CFTypeRef, CFTypeRef);
extern uint64_t CFGetTypeID(CFTypeRef), CFBooleanGetTypeID(void);
extern Boolean CFBooleanGetValue(CFTypeRef);
extern void *dispatch_queue_create(const char *, void *);
extern unsigned sleep(unsigned);
extern int usleep(unsigned), dprintf(int, const char *, ...);
extern uint64_t mach_absolute_time(void);

struct callbacks {
    uint64_t version;
    void (*notification)(void *, void *, HIDService, uint32_t, CFDictionaryRef);
    Boolean (*set)(void *, void *, HIDService, CFStringRef, CFTypeRef);
    CFTypeRef (*copy)(void *, void *, HIDService, CFStringRef);
    HIDEvent (*event)(void *, void *, HIDService, uint32_t, HIDEvent, uint32_t);
    int (*output)(void *, void *, HIDService, HIDEvent);
    CFTypeRef (*matching)(void *, void *, HIDService, CFDictionaryRef);
};
extern HIDClient IOHIDEventSystemClientCreateWithType(void *, int, CFDictionaryRef);
extern void IOHIDEventSystemClientScheduleWithDispatchQueue(HIDClient, void *);
extern HIDService IOHIDVirtualServiceClientCreateWithCallbacks(HIDClient, CFDictionaryRef, const struct callbacks *, void *, void *);
extern Boolean IOHIDVirtualServiceClientRemove(HIDService);
extern Boolean IOHIDVirtualServiceClientDispatchEvent(HIDService, HIDEvent);
extern HIDEvent IOHIDEventCreateDigitizerEvent(void *, uint64_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t,
    double, double, double, double, double, double, Boolean, Boolean, uint32_t);
extern HIDEvent IOHIDEventCreateDigitizerFingerEvent(void *, uint64_t, uint32_t, uint32_t, uint32_t,
    double, double, double, double, double, Boolean, Boolean, uint32_t);
extern HIDEvent IOHIDEventCreateKeyboardEvent(void *, uint64_t, uint32_t, uint32_t, Boolean, uint32_t);
extern void IOHIDEventAppendEvent(HIDEvent, HIDEvent, uint32_t);
extern void IOHIDEventSetIntegerValue(HIDEvent, uint32_t, CFIndex);

static CFStringRef str(const char *s) { return CFStringCreateWithCString(0, s, 0x08000100); }
static CFNumberRef num(int n) { return CFNumberCreate(0, 9, &n); }
static void property(CFMutableDictionaryRef d, const char *key, CFTypeRef value) {
    CFStringRef k = str(key); CFDictionarySetValue(d, k, value); CFRelease(k);
}
struct service_state { CFMutableDictionaryRef properties; volatile unsigned opened; };
static CFStringRef opened_key;
static CFStringRef mode_key;
static volatile int touch_mode;
static CFStringRef queried_keys[48];
static unsigned queried_count;
static CFTypeRef copy_property(void *target, void *ref, HIDService s, CFStringRef key) {
    (void)target; (void)s;
    CFTypeRef value = CFDictionaryGetValue(((struct service_state *)ref)->properties, key);
    unsigned known = 0;
    for (unsigned i = 0; key && i < queried_count; ++i) if (CFEqual(key, queried_keys[i])) known = 1;
    if (key && !known && queried_count < 48) {
        char text[128] = "?";
        queried_keys[queried_count++] = CFRetain(key);
        CFStringGetCString(key, text, sizeof(text), 0x08000100);
        dprintf(2, "odin-host-input: server requests property %s: %s\n", text, value ? "present" : "absent");
    }
    return value ? CFRetain(value) : 0;
}
static Boolean set_property(void *target, void *ref, HIDService s, CFStringRef key, CFTypeRef value) {
    (void)target; (void)s;
    if (key && value && CFEqual(key, opened_key) && CFGetTypeID(value) == CFBooleanGetTypeID() && CFBooleanGetValue(value)) {
        ((struct service_state *)ref)->opened = 1;
        dprintf(2, "odin-host-input: opened by event system\n");
    }
    if (key && value && CFEqual(key, mode_key) && CFGetTypeID(value) == CFNumberGetTypeID()) {
        int mode = 0;
        if (CFNumberGetValue((CFNumberRef)value, 9, &mode)) {
            touch_mode = mode;
            dprintf(2, "odin-host-input: touch detection mode 0x%x\n", mode);
        }
    }
    return 1;
}
static void notification(void *a, void *b, HIDService s, uint32_t type, CFDictionaryRef p) {
    (void)a; (void)b; (void)s; (void)type; (void)p;
}
static const struct callbacks cb = {2, notification, set_property, copy_property, 0, 0, 0};

static HIDService make_buttons(HIDClient client, struct service_state *state) {
    state->properties = CFDictionaryCreateMutable(0, 0, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks);
    state->opened = 0;
    CFMutableDictionaryRef pair = CFDictionaryCreateMutable(0, 0, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks);
    CFNumberRef page = num(12), usage = num(1), zero = num(0);
    property(pair, "DeviceUsagePage", page); property(pair, "DeviceUsage", usage);
    CFArrayRef pairs = CFArrayCreate(0, (const void **)&pair, 1, kCFTypeArrayCallBacks);
    property(state->properties, "PrimaryUsagePage", page); property(state->properties, "PrimaryUsage", usage);
    property(state->properties, "DeviceUsagePage", page); property(state->properties, "DeviceUsage", usage);
    property(state->properties, "DeviceUsagePairs", pairs);
    property(state->properties, "Built-In", kCFBooleanTrue);
    property(state->properties, "Transport", str("SPI"));
    property(state->properties, "Product", str("QEMU-only wake button"));
    property(state->properties, "VendorID", zero); property(state->properties, "ProductID", zero);
    for (unsigned attempt = 0; attempt < 20; ++attempt) {
        state->opened = 0;
        HIDService service = IOHIDVirtualServiceClientCreateWithCallbacks(client, state->properties, &cb, 0, state);
        for (unsigned n = 0; service && n < 20 && !state->opened; ++n) usleep(100000);
        dprintf(2, "odin-host-input: buttons attempt %u service %p opened %u\n", attempt + 1, service, state->opened);
        if (!service || state->opened) return service;
        IOHIDVirtualServiceClientRemove(service); CFRelease(service);
    }
    return 0;
}

static unsigned wake_display(HIDService buttons) {
    unsigned accepted = 0;
    for (unsigned n = 0; n < 2; ++n) {
        HIDEvent event = IOHIDEventCreateKeyboardEvent(0, mach_absolute_time(), 12, 0x30, n == 0, 0);
        if (!event) continue;
        IOHIDEventSetIntegerValue(event, 4, 1);
        accepted += IOHIDVirtualServiceClientDispatchEvent(buttons, event);
        CFRelease(event);
    }
    return accepted;
}

static int send_contact(HIDService service, double y, unsigned down, unsigned mask) {
    uint64_t time = mach_absolute_time();
    HIDEvent hand = IOHIDEventCreateDigitizerEvent(0, time, 3, 0, 0, mask & ~1U, 0,
        0.5, y, 0, 0, 0, 0, down, down, 0);
    HIDEvent finger = IOHIDEventCreateDigitizerFingerEvent(0, time, 1, 2, mask | 0x800,
        0.5, y, 0, down ? 1 : 0, 0, down, down, 0);
    if (!hand || !finger) { if (hand) CFRelease(hand); if (finger) CFRelease(finger); return 0; }
    IOHIDEventSetIntegerValue(hand, 0xb0019, 1);
    IOHIDEventSetIntegerValue(hand, 4, 1);
    IOHIDEventSetIntegerValue(finger, 0xb0019, 1);
    IOHIDEventAppendEvent(hand, finger, 0);
    Boolean accepted = IOHIDVirtualServiceClientDispatchEvent(service, hand);
    CFRelease(finger); CFRelease(hand);
    return accepted;
}

int main(void) {
    dprintf(2, "odin-host-input: QEMU-only finite bottom-edge swipe test\n");
    opened_key = str("DeviceOpenedByEventSystem");
    mode_key = str("TouchDetectionMode");
    struct service_state state = {CFDictionaryCreateMutable(0, 0, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks), 0};
    CFMutableDictionaryRef pair = CFDictionaryCreateMutable(0, 0, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks);
    CFNumberRef page = num(13), usage = num(4), zero = num(0);
    property(pair, "DeviceUsagePage", page); property(pair, "DeviceUsage", usage);
    CFArrayRef pairs = CFArrayCreate(0, (const void **)&pair, 1, kCFTypeArrayCallBacks);
    property(state.properties, "PrimaryUsagePage", page); property(state.properties, "PrimaryUsage", usage);
    property(state.properties, "DeviceUsagePage", page); property(state.properties, "DeviceUsage", usage);
    property(state.properties, "DeviceUsagePairs", pairs);
    property(state.properties, "Built-In", kCFBooleanTrue); property(state.properties, "DisplayIntegrated", kCFBooleanTrue);
    property(state.properties, "Transport", str("SPI")); property(state.properties, "Manufacturer", str("UniXNU Odin host test"));
    property(state.properties, "Product", str("QEMU-only virtual touch"));
    property(state.properties, "VendorID", zero); property(state.properties, "ProductID", zero);
    HIDClient client = 0; HIDService service = 0;
    for (unsigned attempt = 0; attempt < 8 && !state.opened; ++attempt) {
        unsigned type = attempt % 2 == 0 ? 4 : 3;
        if (!client) {
            dprintf(2, "odin-host-input: creating client type %u attempt %u\n", type, attempt + 1);
            client = IOHIDEventSystemClientCreateWithType(0, type, 0);
            if (client) IOHIDEventSystemClientScheduleWithDispatchQueue(client, dispatch_queue_create("odin.host.input", 0));
        }
        if (!client) { sleep(5); continue; }
        dprintf(2, "odin-host-input: creating virtual service type %u\n", type);
        service = IOHIDVirtualServiceClientCreateWithCallbacks(client, state.properties, &cb, 0, &state);
        for (unsigned n = 0; service && n < 50 && !state.opened; ++n) usleep(100000);
        dprintf(2, "odin-host-input: attempt %u client %p service %p opened %u\n", attempt + 1, client, service, state.opened);
        if (!state.opened && service) { IOHIDVirtualServiceClientRemove(service); CFRelease(service); service = 0; }
        if (!state.opened) { CFRelease(client); client = 0; }
    }
    if (!state.opened || !service) return 2;
    struct service_state buttons_state = {0, 0};
    HIDService buttons = make_buttons(client, &buttons_state);
    sleep(120);
    for (unsigned attempt = 0; attempt < 12; ++attempt) {
        dprintf(2, "odin-host-input: before swipe %u detection mode 0x%x\n", attempt + 1, touch_mode);
        if ((touch_mode & 0xff) == 0xfe) {
            if (!buttons || !buttons_state.opened) {
                dprintf(2, "odin-host-input: wake requested but no opened button service; no blind toggle\n");
                break;
            }
            dprintf(2, "odin-host-input: display requested wake; power button accepted %u/2 events\n", wake_display(buttons));
            sleep(5);
            if ((touch_mode & 0xff) != 1) {
                dprintf(2, "odin-host-input: display not in reporting mode after wake; deferring swipe\n");
                sleep(10); continue;
            }
        }
        if ((touch_mode & 0xff) == 0xff) {
            dprintf(2, "odin-host-input: reporting disabled; deferring swipe\n");
            sleep(10); continue;
        }
        unsigned accepted = send_contact(service, 0.985, 1, 3);
        for (unsigned n = 1; n <= 20; ++n) { usleep(25000); accepted += send_contact(service, 0.985 - 0.685 * n / 20, 1, 4); }
        accepted += send_contact(service, 0.3, 0, 3);
        dprintf(2, "odin-host-input: swipe %u accepted %u/22 events (acceptance does not prove UI response)\n", attempt + 1, accepted);
        sleep(10);
    }
    if (buttons) { IOHIDVirtualServiceClientRemove(buttons); CFRelease(buttons); }
    IOHIDVirtualServiceClientRemove(service); CFRelease(service); CFRelease(client);
    dprintf(2, "odin-host-input: finite test complete\n");
    return 0;
}
