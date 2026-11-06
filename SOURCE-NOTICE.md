# Source notices

This is a mixed-license development port. Existing file headers and component license files are retained; this notice does not relicense upstream work.

- UniXNU and the pinned component repositories are identified in `source-pins.json`.
- `drivers/OdinStTouch` and the ST adapter carry GPL-2.0-only headers. Board/protocol references include Xiaomi MiCode source revision `f82406097ede3943a96c08b95bd1f5b5149ee0f0`.
- `drivers/OdinDisplay` and `drivers/RamBlock` retain their component license files.
- HakiOS-derived user-space code retains `host-input/LICENSE.HakiOS` and source attribution. Its user-space MIT notice does not relicense XNU modifications.
- XNU modifications remain subject to their original Apple Public Source License notices and applicable upstream terms. Obtain matching full upstream sources/licenses from the pinned repositories when rebuilding or redistributing derivatives.
- Other files retain their existing SPDX and copyright notices. No blanket license is asserted for files without one.

Reference for the current edge-gesture investigation: `https://github.com/OddlyLabs/unixnu-fuxi`, commit `78f30b651c0ca6ea325682832bb25767523212f5`, `package/NativeHidInput.cpp` (BSD-2-Clause-Patent header). The edge-contact design is adapted in u89; all original-family table sizes, slots and fields were independently qualified against 20F66. Its iPadOS offsets are not reused.

Apple system images, Apple original driver code/binaries, vendor firmware bytes and local credentials are not included in the source publication.

## u85–u88 build disclosure (2026-11-07)

The preserved UniXNU build tools and XnuPrelink parser retain their respective upstream terms; copies of the pinned license files are included at `licenses/UniXNU-LICENSE` and `licenses/XnuPrelink-LICENSE`. `recipes/u85-u88/reference-nx769j` preserves configuration and the prelink helper from Asultop/UniXNU-NX769J revision `2a265afdbd95d45e4a90664157e793c3bfee3755`; existing file notices remain applicable. Imported source receipts are provenance and file-hash lists, not a grant to redistribute system media or vendor firmware. No blanket relicensing is asserted.
