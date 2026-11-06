/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Validate a raw, page-aligned disk in DarwinBoot's reserved payload prefix.
 * No physical address is accepted merely because it occurs in a boot argument.
 */
#ifndef ODIN_RAM_ROOT_RANGE_H
#define ODIN_RAM_ROOT_RANGE_H
static int
odin_ram_root_range_valid(unsigned long long phys, unsigned long long bytes,
    unsigned long long top, unsigned long long tree, unsigned long long tree_bytes,
    unsigned long long disk, unsigned long long disk_bytes)
{
    const unsigned long long limit = ~0ULL;
    if (!bytes || bytes > limit - phys || top < phys || top > phys + bytes)
        return 0;
    if (!tree_bytes || tree < phys || tree > top || tree_bytes > top - tree)
        return 0;
    if (!disk_bytes || disk_bytes > 0xfffff000ULL || ((disk | disk_bytes) & 0xfff))
        return 0;
    if (disk < tree + tree_bytes || disk > top || disk_bytes > top - disk)
        return 0;
    return 1;
}
#endif
