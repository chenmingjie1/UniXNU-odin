/* SPDX-License-Identifier: BSD-2-Clause
 * Original IOSurface -> existing HakiosGPU user-memory selector.
 * This is a transport adapter, not a Metal device or a desktop renderer.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

struct odin_surface_description {
    uint32_t surface, handle;
    uint64_t size;
    uint32_t offset, row_bytes, width, height, format, planes;
};
struct odin_gpu_user_memory {
    uint64_t address, size;
    uint32_t handle, flags;
};
struct odin_surface_import {
    void *surface;
    struct odin_surface_description info;
};
/* Zero or the original IOKit error. Caller serializes this context and its GPU
 * connection. It must wait for ALL uses of a handle before close. Timeout keeps
 * the surface/handle alive; it must never be recycled into another frame.
 */
typedef int (*odin_gpu_call)(void *, uint32_t, void *, size_t);
int odin_surface_import_open(struct odin_surface_import *, uint32_t surface_id,
                            uint32_t connection_page_size, odin_gpu_call, void *);
int odin_surface_import_close(struct odin_surface_import *, odin_gpu_call, void *,
                             int all_gpu_uses_completed);
#ifdef __cplusplus
}
#endif
