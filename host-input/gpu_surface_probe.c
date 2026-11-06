/* SPDX-License-Identifier: BSD-2-Clause
 * One bounded original-IOSurface GPU transport probe, separate from rendering.
 * Never draws onto the panel. A failed/unknown fence retains its resources.
 */
#include "OdinSurfaceImport.h"
extern void *CFDictionaryCreateMutable(const void *, long, const void *, const void *);
extern void CFDictionarySetValue(void *, const void *, const void *);
extern void *CFNumberCreate(const void *, int, const void *);
extern const char kCFTypeDictionaryKeyCallBacks[], kCFTypeDictionaryValueCallBacks[];
extern void *CFStringCreateWithCString(const void *, const char *, unsigned);
extern void CFRelease(const void *);
extern void *IOSurfaceCreate(const void *);
extern uint32_t IOSurfaceGetID(void *);
extern int IOSurfaceLock(void *, uint32_t, uint32_t *);
extern int IOSurfaceUnlock(void *, uint32_t, uint32_t *);
extern void *IOSurfaceGetBaseAddress(void *);
extern size_t IOSurfaceGetAllocSize(void *), IOSurfaceGetWidth(void *), IOSurfaceGetHeight(void *), IOSurfaceGetBytesPerRow(void *);
extern void *dispatch_get_global_queue(long, unsigned long);
extern unsigned mach_task_self(void);
extern unsigned IOServiceGetMatchingService(unsigned, void *);
extern void *IOServiceMatching(const char *);
extern int IOServiceOpen(unsigned, unsigned, unsigned, unsigned *);
extern int IOServiceClose(unsigned);
extern int IOObjectRelease(unsigned);
extern int IOConnectCallStructMethod(unsigned, unsigned, const void *, size_t, void *, size_t *);
extern int IOConnectMapMemory64(unsigned, unsigned, unsigned, uint64_t *, uint64_t *, unsigned);
extern int IOConnectUnmapMemory64(unsigned, unsigned, unsigned, uint64_t);
extern uint64_t mach_continuous_time(void);
extern int mach_timebase_info(void *);
extern int sysctlbyname(const char *, void *, unsigned long *, void *, unsigned long);

static unsigned probe_record[16];
static unsigned probe_connection;
static struct odin_surface_import probe_import;
static int gpu_probe_call(void *connection, uint32_t selector, void *data, size_t size) {
    size_t returned = size;
    int result = IOConnectCallStructMethod(*(unsigned *)connection, selector, data, size, data, &returned);
    if (!result && returned != size) return (int)0xe00002c2u;
    return result;
}
static void gpu_probe_report(unsigned phase, int error) {
    probe_record[0] = 1; probe_record[1] = phase; probe_record[2] = (unsigned)error;
    sysctlbyname("kern.odin_gpu_probe", 0, 0, probe_record, sizeof(probe_record));
}
static unsigned gpu_probe_parity(unsigned n) {
    n ^= n >> 16; n ^= n >> 8; n ^= n >> 4;
    return ((0x6996u >> (n & 15)) & 1) ^ 1;
}
static unsigned gpu_probe_packet(unsigned op, unsigned count) {
    return 0x70000000u | count | gpu_probe_parity(count) << 15 |
        op << 16 | gpu_probe_parity(op) << 23;
}
static int gpu_probe_number(void *dict, const char *key, int64_t value) {
    void *k = CFStringCreateWithCString(0, key, 0x08000100);
    void *n = CFNumberCreate(0, 4, &value); /* kCFNumberSInt64Type */
    if (k && n) CFDictionarySetValue(dict, k, n);
    if (k) CFRelease(k);
    if (n) CFRelease(n);
    return !!k && !!n;
}
static void gpu_surface_probe(void *unused) {
    (void)unused;
    if (probe_record[0]) return;
    gpu_probe_report(1, 0);
    void *dict = CFDictionaryCreateMutable(0, 0, kCFTypeDictionaryKeyCallBacks,
                                          kCFTypeDictionaryValueCallBacks);
    if (!dict) { gpu_probe_report(1, (int)0xe00002bdu); return; }
    int keys = gpu_probe_number(dict, "IOSurfaceWidth", 64) &&
        gpu_probe_number(dict, "IOSurfaceHeight", 64) &&
        gpu_probe_number(dict, "IOSurfaceBytesPerRow", 256) &&
        gpu_probe_number(dict, "IOSurfaceBytesPerElement", 4) &&
        gpu_probe_number(dict, "IOSurfacePixelFormat", 0x42475241) &&
        gpu_probe_number(dict, "IOSurfaceAllocSize", 16384);
    void *surface = keys ? IOSurfaceCreate(dict) : 0;
    CFRelease(dict);
    if (!surface) { gpu_probe_report(2, (int)0xe00002bdu); return; }
    unsigned id = IOSurfaceGetID(surface); probe_record[3] = id;
    int result = IOSurfaceLock(surface, 0, 0);
    if (result) { gpu_probe_report(2, result); CFRelease(surface); return; }
    uint32_t *pixels = IOSurfaceGetBaseAddress(surface);
    int geometry = pixels && IOSurfaceGetAllocSize(surface) >= 16384 &&
        IOSurfaceGetWidth(surface) == 64 && IOSurfaceGetHeight(surface) == 64 &&
        IOSurfaceGetBytesPerRow(surface) == 256;
    if (geometry) for (unsigned i = 0; i < 4096; i++) pixels[i] = 0x11223344;
    result = IOSurfaceUnlock(surface, 0, 0);
    if (!geometry || result) { gpu_probe_report(2, result ? result : (int)0xe00002c2u); CFRelease(surface); return; }
    gpu_probe_report(2, 0);
    unsigned service = IOServiceGetMatchingService(0, IOServiceMatching("HakiosGPU"));
    if (!service) { gpu_probe_report(3, (int)0xe00002f0u); CFRelease(surface); return; }
    result = IOServiceOpen(service, mach_task_self(), 0, &probe_connection);
    IOObjectRelease(service);
    if (result) { gpu_probe_report(3, result); CFRelease(surface); return; }
    gpu_probe_report(3, 0);
    result = odin_surface_import_open(&probe_import, id, 4096, gpu_probe_call, &probe_connection);
    CFRelease(surface); /* import has its own Copy-rule reference if successful */
    if (result) {
        gpu_probe_report(4, result);
        if (!probe_import.surface) { IOServiceClose(probe_connection); probe_connection = 0; }
        return;
    }
    probe_record[4] = probe_import.info.handle; probe_record[5] = (unsigned)probe_import.info.size;
    probe_record[6] = probe_import.info.width; probe_record[7] = probe_import.info.height;
    gpu_probe_report(4, 0);
    struct { uint64_t size; unsigned flags, handle; } command = {4096, 0x20000, 0};
    struct { unsigned handle, info; uint64_t value; unsigned len, pad; } info = {0};
    uint64_t command_map = 0, command_size = 0, target_iova = 0;
    int submitted = 0, completed = 0;
    result = gpu_probe_call(&probe_connection, 0x42, &command, sizeof(command));
    if (result) goto finish;
    info.handle = probe_import.info.handle; info.info = 1;
    result = gpu_probe_call(&probe_connection, 0x43, &info, sizeof(info));
    if (result) goto finish;
    target_iova = info.value;
    info.handle = command.handle; info.info = 1;
    result = gpu_probe_call(&probe_connection, 0x43, &info, sizeof(info));
    if (result) goto finish;
    result = IOConnectMapMemory64(probe_connection, command.handle, mach_task_self(),
                                 &command_map, &command_size, 1);
    if (!result && (!command_map || command_size < 4096)) result = (int)0xe00002c2u;
    if (result) goto finish;
    {
        uint32_t *words = (uint32_t *)(uintptr_t)command_map;
        const unsigned offsets[4] = {0, 2048, 4032, 4095};
        const unsigned values[4] = {0xff0000ff, 0xff00ff00, 0xffff0000, 0xffffffff};
        unsigned count = 0;
        for (unsigned i = 0; i < 4; i++) {
            uint64_t at = target_iova + 4ull * offsets[i];
            words[count++] = gpu_probe_packet(0x3d, 3); /* CP_MEM_WRITE */
            words[count++] = (uint32_t)at; words[count++] = (uint32_t)(at >> 32);
            words[count++] = values[i];
        }
        words[count++] = gpu_probe_packet(0x12, 0); /* CP_WAIT_MEM_WRITES */
        struct { unsigned flags, handle; uint64_t presumed; } bos[2] = {
            {1, command.handle, info.value}, {2, probe_import.info.handle, target_iova}};
        struct { unsigned type, submit_idx, offset, size, pad, relocations; uint64_t relocs; } cmd = {
            1, 0, 0, count * 4, 0, 0, 0};
        struct {
            unsigned flags, fence, nr_bos, nr_cmds; uint64_t bos, cmds;
            int fence_fd; unsigned queue; uint64_t in_sync, out_sync;
            unsigned n_in, n_out, stride, pad;
        } submit = {1, 0, 2, 1, (uintptr_t)bos, (uintptr_t)&cmd, -1, 0, 0, 0, 0, 0, 0, 0};
        _Static_assert(sizeof(submit) == 72 && sizeof(cmd) == 32 && sizeof(bos[0]) == 16, "submit ABI");
        gpu_probe_report(5, 0);
        __asm__ volatile("dsb sy" ::: "memory");
        submitted = 1;
        result = gpu_probe_call(&probe_connection, 0x46, &submit, sizeof(submit));
        probe_record[8] = submit.fence;
        gpu_probe_report(6, result);
        if (result) goto finish;
        struct { unsigned numer, denom; } timebase = {0};
        result = mach_timebase_info(&timebase);
        if (!result && !timebase.denom) result = (int)0xe00002c2u;
        if (result) goto finish;
        uint64_t ticks = mach_continuous_time();
        uint64_t ns = ticks / timebase.denom * timebase.numer +
                      ticks % timebase.denom * timebase.numer / timebase.denom;
        ns += 2000000000ull;
        struct { unsigned fence, flags; int64_t seconds, nanoseconds; unsigned queue; } wait = {
            submit.fence, 0, (int64_t)(ns / 1000000000), (int64_t)(ns % 1000000000), 0};
        _Static_assert(sizeof(wait) == 32, "wait ABI");
        result = gpu_probe_call(&probe_connection, 0x47, &wait, sizeof(wait));
        gpu_probe_report(7, result);
        if (result) goto finish;
        completed = 1;
        result = IOSurfaceLock(probe_import.surface, 1, 0); /* read-only after fence */
        if (result) goto finish;
        pixels = IOSurfaceGetBaseAddress(probe_import.surface);
        unsigned mismatch = 0;
        if (pixels) for (unsigned i = 0; i < 4096; i++) {
            unsigned wanted = 0x11223344;
            for (unsigned j = 0; j < 4; j++) if (i == offsets[j]) wanted = values[j];
            if (pixels[i] != wanted) { ++mismatch; if (!probe_record[10]) {
                probe_record[10] = i + 1; probe_record[11] = pixels[i]; probe_record[12] = wanted;
            } }
        }
        probe_record[9] = pixels ? mismatch : 4096;
        int unlocked = IOSurfaceUnlock(probe_import.surface, 1, 0);
        result = unlocked ? unlocked : probe_record[9] ? (int)0xe00002c9u : 0;
        gpu_probe_report(8, result);
    }
finish:
    if (submitted && !completed) { gpu_probe_report(11, result); return; }
    if (command_map) IOConnectUnmapMemory64(probe_connection, command.handle, mach_task_self(), command_map);
    if (command.handle) {
        unsigned close[2] = {command.handle, 0};
        int closed = gpu_probe_call(&probe_connection, 9, close, sizeof(close));
        if (closed) { gpu_probe_report(12, closed); return; }
    }
    int closed = odin_surface_import_close(&probe_import, gpu_probe_call, &probe_connection, 1);
    if (closed) { gpu_probe_report(12, closed); return; }
    IOServiceClose(probe_connection); probe_connection = 0;
    probe_record[15] = completed && !result;
    gpu_probe_report(10, result);
}
__attribute__((constructor)) static void gpu_probe_start(void) {
    dispatch_after_f(dispatch_time(0, 60000000000LL),
                     dispatch_get_global_queue(0, 0), 0, gpu_surface_probe);
}
