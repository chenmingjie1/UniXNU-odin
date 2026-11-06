#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "../scripts/OdinRamRootRange.h"

int main(void)
{
    const uint64_t phys = 0x200000000ULL, bytes = 0x100000000ULL;
    const uint64_t tree = phys + 0x4000000, tree_bytes = 0x3020;
    const uint64_t disk = phys + 0x4004000, size = 2476732416ULL;
    const uint64_t top = disk + size;
    unsigned checks = 0;
#define EXPECT(expected, p, b, t, dt, dts, d, ds) \
    do { assert(odin_ram_root_range_valid(p,b,t,dt,dts,d,ds) == expected); checks++; } while (0)
    EXPECT(1, phys, bytes, top, tree, tree_bytes, disk, size);
    EXPECT(1, phys, bytes, top, tree, tree_bytes, disk, 4096);
    EXPECT(0, phys, bytes, top-1, tree, tree_bytes, disk, size);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, tree, size);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, disk+1, size);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, disk, size-1);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, disk, 0);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, UINT64_MAX-4095, 8192);
    EXPECT(0, UINT64_MAX-4095, 8192, top, tree, tree_bytes, disk, size);
    EXPECT(0, phys, bytes, phys+bytes+1, tree, tree_bytes, disk, size);
    EXPECT(0, phys, bytes, top, tree, UINT64_MAX, disk, size);
    EXPECT(0, phys, bytes, top, phys-1, tree_bytes, disk, size);
    EXPECT(0, phys, bytes, top, tree, 0, disk, size);
    EXPECT(0, phys, bytes, top, tree, tree_bytes, disk, 0x100000000ULL);
    /* Every byte of a page-unaligned disk address must be rejected. */
    for (unsigned offset=1; offset<4096; offset++) {
        EXPECT(0, phys, bytes, top, tree, tree_bytes, disk+offset, size);
    }
    printf("PASS: %u reserved-RAM range checks, including >4GiB PA and 2.48GB disk\n", checks);
    return 0;
}
