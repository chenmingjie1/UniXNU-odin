/* SPDX-License-Identifier: BSD-2-Clause
 * Mock public API failures and ownership, not a simulated GPU or IOSurface ABI.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "OdinSurfaceImport.h"
static uintptr_t base;
static size_t allocation, width, height, row, planes;
static uint32_t format, id, flags;
static int lookup_failure, lock_error, unlock_error, import_error, close_error;
static unsigned held, locks, imports, closes, releases;
void *IOSurfaceLookup(uint32_t value) {
    if (lookup_failure || value != id) return 0;
    ++held; return (void *)0x1234;
}
void *IOSurfaceGetBaseAddress(void *s) { assert(s); return (void *)base; }
size_t IOSurfaceGetAllocSize(void *s) { assert(s); return allocation; }
size_t IOSurfaceGetWidth(void *s) { assert(s); return width; }
size_t IOSurfaceGetHeight(void *s) { assert(s); return height; }
size_t IOSurfaceGetBytesPerRow(void *s) { assert(s); return row; }
size_t IOSurfaceGetPlaneCount(void *s) { assert(s); return planes; }
uint32_t IOSurfaceGetPixelFormat(void *s) { assert(s); return format; }
uint32_t IOSurfaceGetID(void *s) { assert(s); return id; }
int IOSurfaceLock(void *s, uint32_t opts, uint32_t *seed) {
    assert(s && !opts && !seed);
    if (!lock_error) ++locks;
    return lock_error;
}
int IOSurfaceUnlock(void *s, uint32_t opts, uint32_t *seed) {
    assert(s && !opts && !seed && locks == 1); --locks; return unlock_error;
}
void CFRelease(const void *s) { assert(s && held); --held; ++releases; }
static int call(void *connection, uint32_t selector, void *data, size_t size) {
    assert(connection == (void *)0x5678 && !locks);
    if (selector == 0x7d) {
        ++imports;
        struct odin_gpu_user_memory *m = data;
        assert(size == 24 && m->address == base && m->size == allocation);
        if (import_error) return import_error;
        m->handle = 17; m->flags = flags; return 0;
    }
    assert(selector == 9 && size == 8 && ((uint32_t *)data)[0] == 17);
    ++closes; return close_error;
}
static void reset(void) {
    assert(!held && !locks);
    base = 0x100000; allocation = 0x4000; width = 64; height = 64; row = 256;
    planes = 0; format = 0x42475241; id = 42; flags = 0;
    lookup_failure = lock_error = unlock_error = import_error = close_error = 0;
    imports = closes = releases = 0;
}
static int open_import(struct odin_surface_import *s, unsigned page) {
    return odin_surface_import_open(s, id, page, call, (void *)0x5678);
}
static void rejected(void) {
    struct odin_surface_import s = {0};
    assert(open_import(&s, 4096));
    assert(!s.surface && !s.info.handle && !held && !locks && !imports);
}
int main(void) {
    for (unsigned page = 4096; page <= 16384; page *= 4) {
        reset(); struct odin_surface_import s = {0};
        assert(!open_import(&s, page));
        assert(held == 1 && !locks && imports == 1 && s.info.handle == 17);
        assert(s.info.offset == 0 && s.info.width == 64 && s.info.size == 0x4000);
        assert(open_import(&s, page) && imports == 1); /* busy, no leaked second import */
        assert(odin_surface_import_close(&s, call, (void *)0x5678, 0));
        assert(held == 1 && !closes); /* outstanding GPU use retains both resources */
        close_error = 123;
        assert(odin_surface_import_close(&s, call, (void *)0x5678, 1) == 123);
        assert(held == 1 && s.info.handle == 17);
        close_error = 0;
        assert(!odin_surface_import_close(&s, call, (void *)0x5678, 1));
        assert(!held && releases == 1 && closes == 2);
        assert(!odin_surface_import_close(&s, call, (void *)0x5678, 1) && releases == 1);
    }
    reset(); lookup_failure = 1; rejected();
    reset(); lock_error = 19; rejected();
    reset(); unlock_error = 20; rejected();
    reset(); base = 0; rejected();
    reset(); base++; rejected();
    reset(); base = UINTPTR_MAX - 4095; rejected();
    reset(); allocation++; rejected();
    reset(); allocation = 0; rejected();
    reset(); allocation = (256u << 20) + 4096; rejected();
    reset(); width = 0; rejected();
    reset(); width = 16385; rejected();
    reset(); height = 16385; rejected();
    reset(); row = 252; rejected();
    reset(); row = 257; rejected();
    reset(); height = 65; rejected();
    reset(); planes = 2; rejected();
    reset(); format = 0x34323076; rejected();
    reset(); struct odin_surface_import s = {0};
    assert(open_import(&s, 8192) && !held && !imports);
    import_error = 99;
    assert(open_import(&s, 4096) == 99 && !held && imports == 1);
    reset(); flags = 2;
    assert(open_import(&s, 4096) && !held && closes == 1 && !s.surface);
    reset(); flags = 2; close_error = 77;
    assert(open_import(&s, 4096) == 77 && held && s.info.handle == 17);
    close_error = 0;
    assert(!odin_surface_import_close(&s, call, (void *)0x5678, 1) && !held);
    puts("surface import: alignment, bounds, write permissions, failures and retained lifetime passed");
}
