/* Finite QEMU-only request to the original iOS16.5 SpringBoard service.
 * No injection, credential entry, Apple executable changes, or physical input.
 * Method signatures and authorization checked in u56-verified-unlock-contract.json.
 */
typedef void *id;
typedef void *Class;
typedef void *SEL;
extern id objc_getClass(const char *);
extern SEL sel_registerName(const char *);
extern void objc_msgSend(void);
extern void *class_getInstanceMethod(Class, SEL);
extern void *dlopen(const char *, int);
extern const char *dlerror(void);
extern int dprintf(int, const char *, ...);
extern void exit(int);
extern void dispatch_main(void);
extern unsigned long long dispatch_time(unsigned long long, long long);
extern void dispatch_after_f(unsigned long long, void *, void *, void (*)(void *));
extern void *dispatch_get_global_queue(long, unsigned long);
static id service, options;
static unsigned requests, completed;

static id msg(id object, const char *name) {
    return ((id (*)(id, SEL))objc_msgSend)(object, sel_registerName(name));
}

static void finished(void *context) {
    (void)context;
    dprintf(2, "odin-host-input: unlock request timeout: requests %u callbacks %u; UI must be checked separately\n", requests, completed);
    exit(completed ? 0 : 3);
}

static void request(void *context) {
    (void)context;
    dprintf(2, "odin-host-input: loading original SBS framework\n");
    if (!dlopen("/System/Library/PrivateFrameworks/SpringBoardServices.framework/SpringBoardServices", 2)) {
        dprintf(2, "odin-host-input: SBS load failed: %s\n", dlerror()); exit(2);
    }
    Class cls = objc_getClass("SBSLockScreenService"), opt = objc_getClass("SBSUnlockOptions");
    SEL selector = sel_registerName("requestPasscodeUnlockUIWithOptions:withCompletion:");
    if (!cls || !opt || !class_getInstanceMethod(cls, selector)) {
        dprintf(2, "odin-host-input: exact SBS class/method missing\n"); exit(2);
    }
    dprintf(2, "odin-host-input: initializing original SBS service\n");
    service = msg(msg(cls, "alloc"), "init");
    options = msg(msg(opt, "alloc"), "init");
    if (!service || !options) { dprintf(2, "odin-host-input: SBS initialization failed\n"); exit(2); }
    dprintf(2, "odin-host-input: request original SBS unlock UI once (not proof of desktop)\n");
    ++requests;
    ((void (*)(id, SEL, id, void (^)(unsigned char)))objc_msgSend)(service, selector, options, ^(unsigned char success) {
        ++completed;
        dprintf(2, "odin-host-input: SBS completion success %u (not proof of desktop)\n", (unsigned)success);
    });
}

int main(void) {
    dprintf(2, "odin-host-input: QEMU-only finite original SBS unlock UI request\n");
    request(0);
    dispatch_after_f(dispatch_time(0, 300000000000LL), dispatch_get_global_queue(0, 0), 0, finished);
    dispatch_main();
    return 0;
}
