// SPDX-License-Identifier: BSD-2-Clause-Patent
// Exact iOS16.5 original accessors, qualified by audit_ios16_surface.py.
// The +48 member is a map; backing descriptor is +56 in this release.
#pragma once
#include <IOKit/IOMemoryDescriptor.h>
extern "C" {
IOMemoryDescriptor *odin_surface_descriptor(OSObject *);
uint32_t odin_surface_width(OSObject *);
uint32_t odin_surface_height(OSObject *);
uint32_t odin_surface_stride(OSObject *);
uint32_t odin_surface_format(OSObject *);
uint32_t odin_surface_allocation(OSObject *);
uint32_t odin_surface_planes(OSObject *);
extern volatile uint32_t odin_surface_inspections[16];
}
