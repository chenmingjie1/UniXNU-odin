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
