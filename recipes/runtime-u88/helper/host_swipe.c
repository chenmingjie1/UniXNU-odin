/* QEMU-only narrow adaptation of HakiOS inject_sb.c's unlock() and autounlock.
 * Upstream: 88513176b1e96ecf0b764cd62c6f4e6ac71345e3, MIT, LICENSE.HakiOS.
 * Runs only when the original loader permits this signed library. No hooks,
 * authentication code edits, input synthesis, or renderer modifications.
 */
typedef void *id;
typedef void *Class;
typedef void *SEL;
extern id objc_getClass(const char *);
extern SEL sel_registerName(const char *);
extern void objc_msgSend(void);
extern void *class_getInstanceMethod(Class, SEL), *class_getClassMethod(Class, SEL);
extern int open(const char *, int, ...), dprintf(int, const char *, ...), close(int), getpid(void);
extern unsigned long long dispatch_time(unsigned long long, long long);
extern void dispatch_after_f(unsigned long long, void *, void *, void (*)(void *));
extern char _dispatch_main_q;
static unsigned attempts;

static void log_result(const char *stage, int result) {
    int fd = open("/private/var/tmp/odin-sb-unlock.log", 0x209, 0644);
    if (fd < 0) return;
    dprintf(fd, "odin-sb-unlock: pid %d attempt %u %s %d\n", getpid(), attempts, stage, result);
    close(fd);
}

static void unlock(void *context) {
    (void)context;
    ++attempts;
    Class cls = objc_getClass("SBLockScreenManager");
    SEL shared = sel_registerName("sharedInstance"), locked = sel_registerName("isUILocked");
    SEL request = sel_registerName("unlockUIFromSource:withOptions:");
    if (!cls || !class_getClassMethod(cls, shared) || !class_getInstanceMethod(cls, locked) ||
        !class_getInstanceMethod(cls, request)) { log_result("original methods unavailable", 0); return; }
    id manager = ((id (*)(Class, SEL))objc_msgSend)(cls, shared);
    if (!manager) {
        log_result("manager not initialized", 0);
    } else if (!((unsigned char (*)(id, SEL))objc_msgSend)(manager, locked)) {
        log_result("UI lock absent; inspect actual scanout", 1);
        return;
    } else {
        /* Original 20F66 method takes int source, not long. 24 is upstream's
         * cover-sheet source; a true answer alone is not a desktop proof. */
        unsigned char result = ((unsigned char (*)(id, SEL, int, id))objc_msgSend)(manager, request, 24, 0);
        log_result("original unlock request answered", result);
    }
    if (attempts < 3)
        dispatch_after_f(dispatch_time(0, 10000000000LL), &_dispatch_main_q, 0, unlock);
}

__attribute__((constructor)) static void start(void) {
    log_result("signed component loaded", 1);
    dispatch_after_f(dispatch_time(0, 10000000000LL), &_dispatch_main_q, 0, unlock);
}

/* MIX 4 / iOS16.5: replace UIKit's unsupported-size status bar provider.
 * Adapted from HakiOS inject_sb.c, pinned 2631f5d7d4f9d7322aca60991b34ba465dec343b.
 * MIT; see LICENSE.HakiOS. No UIKit initialization or UIScreen calls here.
 */
typedef void *id;
typedef void *Class;
typedef void *SEL;
typedef void *Method;
typedef void (*IMP)(void);
extern Class objc_getClass(const char *), object_getClass(id), class_getSuperclass(Class);
extern SEL sel_registerName(const char *), method_getName(Method);
extern void objc_msgSend(void);
extern Method *class_copyMethodList(Class, unsigned *);
extern IMP method_getImplementation(Method), class_replaceMethod(Class, SEL, IMP, const char *);
extern const char *method_getTypeEncoding(Method);
extern int strcmp(const char *, const char *), open(const char *, int, ...);
extern int dprintf(int, const char *, ...), close(int);
extern void free(void *);
static Class split;

static id fallback_alloc(id self, SEL selector) {
    (void)self;
    return ((id (*)(Class, SEL))objc_msgSend)(split, selector);
}
static id fallback_alloc_zone(id self, SEL selector, void *zone) {
    (void)self;
    return ((id (*)(Class, SEL, void *))objc_msgSend)(split, selector, zone);
}
static void log_status(const char *message, unsigned count) {
    int fd = open("/private/var/tmp/odin-statusbar.log", 0x209, 0644);
    if (fd >= 0) {
        dprintf(fd, "odin-statusbar: %s (%u)\n", message, count);
        close(fd);
    }
}
__attribute__((constructor)) static void statusbar_start(void) {
    Class fallback = objc_getClass("_UIStatusBarVisualProvider_Fallback");
    split = objc_getClass("_UIStatusBarVisualProvider_Split1080");
    if (!fallback || !split) { log_status("required original classes absent", 0); return; }
    Class chain[8];
    unsigned depth = 0, count = 0;
    int common = 0;
    for (Class c = split; c && depth < 8; c = class_getSuperclass(c)) {
        unsigned parents = 0;
        for (Class f = fallback; f && parents++ < 32; f = class_getSuperclass(f))
            if (f == c) { common = 1; break; }
        if (common) break;
        chain[depth++] = c;
    }
    if (!common) { log_status("provider ancestry not qualified", 0); return; }
    Class meta = object_getClass(fallback);
    while (depth) {
        unsigned total = 0;
        Method *methods = class_copyMethodList(object_getClass(chain[--depth]), &total);
        if (!methods && total) { log_status("method enumeration failed", count); return; }
        for (unsigned i = 0; i < total; ++i) {
            SEL selector = method_getName(methods[i]);
            /* Selector identity is stable; exclude allocation and runtime startup. */
            if (selector != sel_registerName("load") && selector != sel_registerName("initialize") &&
                selector != sel_registerName("alloc") && selector != sel_registerName("allocWithZone:")) {
                class_replaceMethod(meta, selector, method_getImplementation(methods[i]), method_getTypeEncoding(methods[i]));
                ++count;
            }
        }
        free(methods);
    }
    class_replaceMethod(meta, sel_registerName("alloc"), (IMP)fallback_alloc, "@16@0:8");
    class_replaceMethod(meta, sel_registerName("allocWithZone:"), (IMP)fallback_alloc_zone, "@24@0:8^v16");
    log_status("original Split1080 provider installed", count);
}

#define ODIN_IDLE_ASSERTION_POLICY 1

/* iOS16.5 RAM fixture: observe original SpringBoard display/input policy.
 * Appended to the existing signed UI component. All calls run on its main queue
 * and require the runtime's exact method type. No event injection or hooks.
 * A fixed, opt-in kernel command requests the original undim/idle reset API.
 */
extern int sysctlbyname(const char *, void *, unsigned long *, void *, unsigned long);
static unsigned policy_ticks, policy_calls;
#ifdef ODIN_IDLE_DISABLE_POLICY
static unsigned policy_idle_owned;
#endif
#ifdef ODIN_SYSTEM_IDLE_POLICY
static unsigned policy_system_owned;
#endif
#ifdef ODIN_IDLE_ASSERTION_POLICY
extern void *CFStringCreateWithCString(const void *, const char *, unsigned);
extern void CFRelease(const void *);
extern id objc_retain(id);
extern void objc_release(id);
static id policy_idle_assertion;
#endif
static int policy_equal(const char *a, const char *b) {
    if (!a || !b) return 0;
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}
static int policy_has(id object, const char *name, const char *types) {
    if (!object) return 0;
    void *method = class_getInstanceMethod(object_getClass(object), sel_registerName(name));
    return method && policy_equal(method_getTypeEncoding(method), types);
}
static unsigned policy_bool(id object, const char *name) {
    if (!policy_has(object, name, "B16@0:8")) return 255;
    return ((unsigned char (*)(id, SEL))objc_msgSend)(object, sel_registerName(name));
}
static id policy_shared(const char *name) {
    Class cls = objc_getClass(name);
    if (!cls) return 0;
    void *method = class_getClassMethod(cls, sel_registerName("sharedInstance"));
    if (!method || !policy_equal(method_getTypeEncoding(method), "@16@0:8")) return 0;
    return ((id (*)(Class, SEL))objc_msgSend)(cls, sel_registerName("sharedInstance"));
}
static void policy_poll(void *unused) {
    (void)unused;
    unsigned record[16] = {1, ++policy_ticks};
    unsigned command = 0;
    unsigned long size = sizeof(command);
    record[11] = (unsigned)sysctlbyname("kern.odin_ui_policy_command", &command, &size, 0, 0);
    record[2] = command;
    id app = 0;
    Class cls = objc_getClass("UIApplication");
    if (cls && class_getClassMethod(cls, sel_registerName("sharedApplication")))
        app = ((id (*)(Class, SEL))objc_msgSend)(cls, sel_registerName("sharedApplication"));
    id backlight = policy_shared("SBBacklightController");
    record[3] = !!app | (!!backlight << 1);
    record[4] = policy_bool(backlight, "screenIsOn");
    record[5] = policy_bool(backlight, "isDigitizerDisabled");
    record[6] = policy_bool(app, "isIdleTimerDisabled");
    record[7] = policy_bool(backlight, "screenIsDim");
    record[8] = policy_bool(app, "isLocked");
#ifdef ODIN_IDLE_ASSERTION_POLICY
    id coordinator = policy_shared("SBIdleTimerGlobalCoordinator");
    record[13] = 4;
    if (coordinator) record[3] |= 4;
    if (command == 1 && !policy_idle_assertion && policy_has(coordinator,
            "acquireIdleTimerDisableAssertionForReason:", "@24@0:8@16")) {
        id reason = CFStringCreateWithCString(0, "MIX4 RAM desktop observation", 0x08000100);
        if (reason) {
            id token = ((id (*)(id, SEL, id))objc_msgSend)(coordinator,
                sel_registerName("acquireIdleTimerDisableAssertionForReason:"), reason);
            if (token) {
                policy_idle_assertion = objc_retain(token);
                ++policy_calls;
            }
            CFRelease(reason);
        }
    } else if (command == 0 && policy_idle_assertion) {
        if (policy_has(policy_idle_assertion, "invalidate", "v16@0:8"))
            ((void (*)(id, SEL))objc_msgSend)(policy_idle_assertion, sel_registerName("invalidate"));
        objc_release(policy_idle_assertion);
        policy_idle_assertion = 0;
        ++policy_calls;
    }
    if (policy_idle_assertion) record[3] |= 8;
    record[12] = policy_bool(coordinator, "isIdleTimerDisabled");
    record[14] = policy_bool(coordinator, "_hasIdleTimerDisableAssertions");
    record[15] = policy_bool(coordinator, "_areIdleTimerDisableAssertionsPrevented");
#elif defined(ODIN_SYSTEM_IDLE_POLICY)
    /* Exact original SBBacklightController entrypoints delegate to the
     * system idle coordinator with a stable original reason string. */
    record[13] = 3;
    if (command == 1 && !policy_system_owned &&
            policy_has(backlight, "preventIdleSleep", "v16@0:8")) {
        ((void (*)(id, SEL))objc_msgSend)(backlight, sel_registerName("preventIdleSleep"));
        policy_system_owned = 1;
        ++policy_calls;
    } else if (command == 0 && policy_system_owned &&
            policy_has(backlight, "allowIdleSleep", "v16@0:8")) {
        ((void (*)(id, SEL))objc_msgSend)(backlight, sel_registerName("allowIdleSleep"));
        policy_system_owned = 0;
        ++policy_calls;
    }
    record[12] = policy_system_owned;
#elif defined(ODIN_IDLE_DISABLE_POLICY)
    /* Use the public original idle-disable API before auto-lock occurs.
     * This does not claim to wake an already locked/off screen. Restore only
     * an assertion this helper itself acquired when observation is requested.
     */
    record[13] = 2;
    if (policy_has(app, "setIdleTimerDisabled:", "v20@0:8B16")) {
        if (command == 1 && policy_bool(app, "isIdleTimerDisabled") == 0) {
            ((void (*)(id, SEL, unsigned char))objc_msgSend)(app,
                sel_registerName("setIdleTimerDisabled:"), 1);
            policy_idle_owned = 1;
            ++policy_calls;
        } else if (command == 0 && policy_idle_owned) {
            ((void (*)(id, SEL, unsigned char))objc_msgSend)(app,
                sel_registerName("setIdleTimerDisabled:"), 0);
            policy_idle_owned = 0;
            ++policy_calls;
        }
    }
    record[12] = policy_bool(app, "isIdleTimerDisabled");
#else
    if (command == 1 && policy_has(app, "resetIdleTimerAndUndim", "v16@0:8")) {
        ((void (*)(id, SEL))objc_msgSend)(app, sel_registerName("resetIdleTimerAndUndim"));
        ++policy_calls;
    }
#endif
    record[9] = policy_calls;
    record[10] = policy_bool(backlight, "screenIsOn");
    sysctlbyname("kern.odin_ui_policy", 0, 0, record, sizeof(record));
    if (policy_ticks < 720)
        dispatch_after_f(dispatch_time(0, 5000000000LL), &_dispatch_main_q, 0, policy_poll);
}
__attribute__((constructor)) static void policy_start(void) {
    dispatch_after_f(dispatch_time(0, 10000000000LL), &_dispatch_main_q, 0, policy_poll);
}
