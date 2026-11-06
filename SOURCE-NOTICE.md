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

## 构建输入补充（2026-11-07）

SDK Release 附件是基于 Theos iPhoneOS16.5 SDK 的本地 XNU 扩展包，保留原有文件与声明；加入的 LLVM 14.0.6 profile runtime / libdispatch firehose 库来源见 `docs/BUILD-INPUTS.md`。它们不因本项目发布而统一改用 MIT。IIG 生成源码保留其原有 Apple 版权和许可头，生成器来源与 revision 同见该文档。

`recipes/u80-root/upstream` 保留 HakiOS `oosexgang/hackios-xnu-kernel@88513176b1e96ecf0b764cd62c6f4e6ac71345e3` 的 APFS 工具与获取 / 构建脚本；MIT 文本见 `upstream/LICENSE-HakiOS`。core launch policy 来自 `bangprovn/ios-fuxi@27f6a31c8b27c6f9127f9cf27092968422579ccf`，文件内完整 MIT 声明保留。历史辅助程序保留源代码、链接 stub 和构建记录；Release 未附完整 Apple 系统 APFS、IPSW、厂商固件或私钥。
