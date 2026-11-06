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
