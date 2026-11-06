/* SPDX-License-Identifier: BSD-2-Clause
 * Uses public original IOSurface exports, not MiniIOSurface or kernel offsets.
 * Only page-aligned, non-planar BGRA surfaces are accepted at this stage.
 * The renderer must provide producer/consumer fence synchronization separately.
 */
#include "OdinSurfaceImport.h"

/* SDK-independent declarations of the public C ABI, with exact-cache export
 * qualification by build_odin_surface_import.py. IOSurfaceLookup is Copy-rule.
 */
extern void *IOSurfaceLookup(uint32_t);
extern void *IOSurfaceGetBaseAddress(void *);
extern size_t IOSurfaceGetAllocSize(void *);
extern size_t IOSurfaceGetWidth(void *);
extern size_t IOSurfaceGetHeight(void *);
extern size_t IOSurfaceGetBytesPerRow(void *);
extern size_t IOSurfaceGetPlaneCount(void *);
extern uint32_t IOSurfaceGetPixelFormat(void *);
extern uint32_t IOSurfaceGetID(void *);
extern int IOSurfaceLock(void *, uint32_t, uint32_t *);
extern int IOSurfaceUnlock(void *, uint32_t, uint32_t *);
extern void CFRelease(const void *);

enum { success = 0, bad_argument = (int)0xe00002c2u,
       not_found = (int)0xe00002f0u, unsupported = (int)0xe00002c7u,
       busy = (int)0xe00002d5u, user_memory = 0x7d, gem_close = 0x09 };
_Static_assert(sizeof(struct odin_surface_description) == 40, "surface wire ABI");
_Static_assert(sizeof(struct odin_gpu_user_memory) == 24, "userptr wire ABI");

int odin_surface_import_open(struct odin_surface_import *out, uint32_t id,
                            uint32_t page, odin_gpu_call call, void *connection)
{
    if (!out || !call || !id || (page != 4096 && page != 16384))
        return bad_argument;
    if (out->surface || out->info.handle) return busy;
    void *surface = IOSurfaceLookup(id);
    if (!surface) return not_found;
    if (IOSurfaceGetID(surface) != id) {
        CFRelease(surface);
        return bad_argument;
    }
    int result = IOSurfaceLock(surface, 0, 0);
    if (result) {
        CFRelease(surface);
        return result;
    }
    uintptr_t base = (uintptr_t)IOSurfaceGetBaseAddress(surface);
    uint64_t size = IOSurfaceGetAllocSize(surface);
    uint64_t width = IOSurfaceGetWidth(surface), height = IOSurfaceGetHeight(surface);
    uint64_t row = IOSurfaceGetBytesPerRow(surface);
    uint32_t format = IOSurfaceGetPixelFormat(surface);
    struct odin_surface_import candidate = {0};
    if (IOSurfaceGetPlaneCount(surface) || format != 0x42475241u ||
        !base || (base & (page - 1)) || !size || (size & (page - 1)) ||
        size > (256u << 20) || size > UINTPTR_MAX - base ||
        !width || width > 16384 || !height || height > 16384 ||
        row < width * 4 || row > UINT32_MAX || (row & 3) || height > size / row) {
        result = unsupported;
    } else {
        candidate.surface = surface;
        candidate.info = (struct odin_surface_description){
            id, 0, size, 0, (uint32_t)row, (uint32_t)width, (uint32_t)height, format, 0};
    }
    /* Do not hold an IOSurface CPU write lock for an entire texture lifetime.
     * Wire only after unlocking, so an unlock failure cannot strand a GPU handle.
     */
    int unlocked = IOSurfaceUnlock(surface, 0, 0);
    if (!result && unlocked) result = unlocked;
    if (!result) {
        struct odin_gpu_user_memory memory = {(uint64_t)base, size, 0, 0};
        result = call(connection, user_memory, &memory, sizeof(memory));
        if (!result) {
            /* userBuffer can fall back to read-only backing. A desktop render
             * target must be writable: do not silently accept that fallback.
             */
            candidate.info.handle = memory.handle;
            if (!memory.handle || (memory.flags & 2)) {
                if (memory.handle) {
                    uint32_t close[2] = {memory.handle, 0};
                    int closed = call(connection, gem_close, close, sizeof(close));
                    if (closed) {
                        *out = candidate; /* caller must retry close; no use submitted */
                        return closed;
                    }
                }
                result = unsupported;
            }
        }
    }
    if (result) CFRelease(surface);
    else *out = candidate;
    return result;
}

int odin_surface_import_close(struct odin_surface_import *context,
                             odin_gpu_call call, void *connection, int completed)
{
    if (!context || !call) return bad_argument;
    if (!context->surface && !context->info.handle) return success;
    if (!context->surface || !context->info.handle) return bad_argument;
    if (!completed) return busy;
    uint32_t close[2] = {context->info.handle, 0};
    int result = call(connection, gem_close, close, sizeof(close));
    if (result) return result;
    CFRelease(context->surface);
    *context = (struct odin_surface_import){0};
    return success;
}
