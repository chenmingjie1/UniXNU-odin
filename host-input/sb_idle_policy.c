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
