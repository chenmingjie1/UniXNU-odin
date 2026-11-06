# SDK、IIG 与 u80 系统生成资料

本页补充 u85～u88 实际构建曾依赖、此前没有随源码提供的 SDK 和 IIG 缓存。文件已作为公开 Release 附件提供，源码与生成记录也可在仓库审阅。

**[下载构建依赖 Release](https://github.com/chenmingjie1/UniXNU-odin/releases/tag/build-inputs-ios16.5-xnu8796-20261107)**

| 附件 | 内容 |
| --- | --- |
| `iPhoneOS16.5.xnu.sdk-with-kernel-libs.tar.gz` | 完整展开符号链接的 SDK，含 `libcc_kext.a`、`libfirehose_kernel.a`、`libpthread_kext.a` |
| `iig-8796-cached-native8796.tar.gz` | wrapper、`native8796/generated`、`legacy-headers`、`headers`、验证和安装记录；含生成源码及 `.cpo` 对象 |
| `native-iig-evidence-20261103.tar.gz` | 既有 prelink 审计使用的原始历史证据包，保持原 SHA256 |
| `u80-root-replay-support.tar.gz` | u59 / u80 历史辅助程序源码、签名 Mach-O、链接 stub、审计和 u39 development trust 元数据 |
| `sdk-package-manifest.json` / `iig-package-manifest.json` | 逐文件大小与 SHA256 |
| `SHA256SUMS.txt` | Release 附件校验值 |

## 下载与校验

以下命令在 Linux 中运行，将三个压缩包和校验清单下载到当前目录：

```bash
base=https://github.com/chenmingjie1/UniXNU-odin/releases/download/build-inputs-ios16.5-xnu8796-20261107
curl -fLO "$base/iPhoneOS16.5.xnu.sdk-with-kernel-libs.tar.gz"
curl -fLO "$base/iig-8796-cached-native8796.tar.gz"
curl -fLO "$base/u80-root-replay-support.tar.gz"
curl -fLO "$base/SHA256SUMS.txt"
sha256sum --check --ignore-missing SHA256SUMS.txt
```

两个主要包的固定值：

```text
cff6c15c0bd6452e360d24fb3c9e7838b170f56df8dfc48bccbab1bb6f47c722  iPhoneOS16.5.xnu.sdk-with-kernel-libs.tar.gz
057d04292d2bd6d346262e3fa9b212d29d4f350d24d445a5ee81b5ab309e7fd8  iig-8796-cached-native8796.tar.gz
```

所有附件的大小与哈希另见 [`assets.json`](../recipes/build-inputs/assets.json)。解压前应先校验；在空的目标目录中安装。

## SDK 安装路径

SDK 压缩包原来含有指向旧虚拟机 Theos 目录的绝对符号链接。此次已展开为实际文件，压缩包中没有悬空链接。它包含 9,093 个 SDK 文件。

原脚本使用 `/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk`。保留原路径时：

```bash
mkdir -p /home/odin/xnu-work/project/xnu-deps/sdk
tar -xzf iPhoneOS16.5.xnu.sdk-with-kernel-libs.tar.gz \
  -C /home/odin/xnu-work/project/xnu-deps/sdk
export XNU_SDK_PATH=/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk
export KERNEL_SDKROOT="$XNU_SDK_PATH"
export XNU_SDK_VERSION=16.5
test -f "$XNU_SDK_PATH/usr/local/lib/kernel/libfirehose_kernel.a"
test -f "$XNU_SDK_PATH/usr/local/lib/kernel/libcc_kext.a"
```

`libcc_kext.a` 在原构建树中是单独构建的 LLVM profile runtime，并非 SDK 原有文件。此次另放入 SDK 的 `usr/local/lib/kernel/`，便于完整取得。原链接脚本仍从下面的位置读取它：

```bash
mkdir -p /home/odin/unixnu-odin-build/upstream/build/cc-kext-llvm14
cp "$XNU_SDK_PATH/usr/local/lib/kernel/libcc_kext.a" \
  /home/odin/unixnu-odin-build/upstream/build/cc-kext-llvm14/libcc_kext.a
```

若改用自己的目录，需要同步修改 [`build_offline_kernel.sh`](../recipes/u85-u88/guest/build_offline_kernel.sh) 中的 `XNUDEPS` / SDK / platform 路径和最终链接脚本。SDK 包没有替代 `xnu-deps/host/bin`、`hostinc`、`AvailabilityVersions`、platform 目录、GNU Make、Clang、ld64、MIG 等其他构建前提。

### SDK 来源

这是基于 Theos `iPhoneOS16.5.sdk` 加入本地 `usr/local` 扩展的 XNU SDK，不是未经修改的完整 Xcode SDK。包内保留原文件与声明。DriverKit 头文件输入来自 macOS 13.3 SDK：

```text
https://github.com/joseluisq/macosx-sdks/releases/download/13.3/MacOSX13.3.sdk.tar.xz
```

`libfirehose_kernel.a` 来自 libdispatch `libdispatch-1415.100.11`，revision `a641558f447659d90ad002ef0ee6f0212273fbfc`。`libcc_kext.a` 来自 LLVM 14.0.6 profile runtime，revision `f28c006a5895fc0e329fe15fead81e37457cb1d1`，本项目入口为 [`build_profile_runtime.py`](../scripts/build_profile_runtime.py)。SDK 清单记录了此次补入 cc archive 的来源。

## IIG 缓存安装与使用

完整压缩包含 17 组 XNU 8796 适配结果。所有生成 `.iig.cpp` 的哈希均已核对 `verification.json`，并保留 `sizeof(IORPC) == 24` 检查。

```bash
mkdir -p /home/odin/unixnu-odin-build
tar -xzf iig-8796-cached-native8796.tar.gz -C /home/odin/unixnu-odin-build
chmod +x /home/odin/unixnu-odin-build/iig-tools/iig-8796-cached
export IIG=/home/odin/unixnu-odin-build/iig-tools/iig-8796-cached
```

wrapper 的 `root` 固定为 `/home/odin/unixnu-odin-build/iig-tools/native8796`。使用其他目录时只调整 wrapper 的路径；不要为了通过检查改写生成源码或输入哈希。它逐项检查原 `.iig` 输入与适配后 `.iig.cpp`，再复制对应 legacy header 和实现，不能处理未包含或已变更的输入。

可在线浏览 [`native8796/generated`](../recipes/build-inputs/iig-tools/native8796/generated)、[`legacy-headers`](../recipes/build-inputs/iig-tools/native8796/legacy-headers) 和 [`verification.json`](../recipes/build-inputs/iig-tools/native8796/verification.json)。`.cpo` 与日志在完整 Release 包中。生成器来源为 `Nyktis/iig-port` revision `ea6d147d668ca15d490da638012243fcd705f30d`；源码构建与安装入口为 [`build_native_iig.py`](../scripts/build_native_iig.py)、[`install_native_iig.py`](../scripts/install_native_iig.py)。

### 保留既有审计包

`audit_ios16_prelink.py` 使用的是另一份历史归档的固定哈希。此次把那份原包也附上，不能把新安装包改名冒充它：

```bash
curl -fLO "$base/native-iig-evidence-20261103.tar.gz"
sha256sum --check --ignore-missing SHA256SUMS.txt
mkdir -p build/ios16-prelink
cp native-iig-evidence-20261103.tar.gz build/ios16-prelink/
```

原审计包 SHA256 为 `2500d7429239795055a71e704622bc5c9f0232b6d89a9ef1acc9ce2bbf597df8`。未放宽审计脚本的 pin。

## System 介质

[`system-host-input-u80.apfs` 获取与生成说明](SYSTEM-HOST-INPUT-U80.md) 包含 Apple CDN 地址、原始 DMG 名称、HakiOS 基础介质构建入口、u10～u80 转换链、辅助程序和 trust bundle 的配置方法。

本次已提供 SDK、完整 IIG 缓存和系统生成资料；仍未从全新环境验证整个内核与用户态的端到端同哈希重建。原始 System / Data、原版驱动介质、厂商固件和其他历史 ABI/provider 输入仍按原构建流程分别准备。各上游文件继续适用自己的许可与声明，参见 [SOURCE-NOTICE.md](../SOURCE-NOTICE.md)。
