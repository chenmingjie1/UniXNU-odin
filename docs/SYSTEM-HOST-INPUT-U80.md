# system-host-input-u80.apfs 获取与生成

`system-host-input-u80.apfs` 是本项目逐步生成的 RAM System 介质。**它没有对应的 Apple 官方同名下载文件。** 这里公开原始介质来源、实际转换链、历史辅助程序、配置和校验值；完整 APFS 不在本次附件中。

## 1. 从 Apple 获取 20F66 输入

实际输入为 iPhone X 的 iOS 16.5 / `20F66`。官方 IPSW 地址：

[iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw](https://updates.cdn-apple.com/2023SpringFCS/fullrestores/032-85130/6AB0D10A-8AF9-4F6C-8CF5-A1B315CABE88/iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw)

IPSW 大小为 `6,165,698,198` 字节。HakiOS 的 `fetch-from-ipsw.py` 可通过 HTTP Range 取出需要的成员，`fetch.sh` 负责选择、解压与布局：

| 成员 | 用途 | 已保留 SHA256 |
| --- | --- | --- |
| `096-04088-077.dmg` | 原始 rootfs | `64354ba3475d3c34d6fc531f75585a7b24af0fdb7a3a8a2bdf95c7f351a3f290` |
| `096-04666-078.dmg` | OS Cryptex / arm64 dyld cache | `2279bf443856fcb6a3f00b1fa06a32ba02a66fdf6ab6b12019462c7498aafdd3` |
| `096-03536-083.dmg` | App Cryptex | 以 IPSW 成员与 BuildManifest 核对；此处不虚构未核验值 |

在 Linux 使用与保留开发树相同的 HakiOS revision：

```bash
git clone https://github.com/oosexgang/hackios-xnu-kernel.git hakios
cd hakios
git checkout 88513176b1e96ecf0b764cd62c6f4e6ac71345e3
KEEP=1 bash sysimage/fetch.sh
```

需要 Python 3、支持 APFS 的 7-Zip 23 或更新版本、C 编译器及 `xnu-deps/build/lzbitmap` 的 `unzbm.c` / `libzbitmap.c`。后两项由 HakiOS 的依赖准备流程提供；`fetch.sh` 会构建 `unzbm`。字体裁剪等依赖以该固定版本脚本为准。不要只复制本仓库的 `fetch.sh` 快照到空目录执行，周边工具也必须存在。

取得后应保留 `sysimage/rootfs` 中完整的原始 LaunchDaemons，后续转换需要它们。HakiOS 的 `system.apfs` 构建入口：

```bash
REST=1 SYSTEM=1 bash userland/build.sh
```

该入口通过选定 rootfs、Cryptex、dyld cache 和 `stage0` 构造 `userland/system.apfs`，使用 `tools/apfs/mkapfs.py` 生成 APFS；它不是将 DMG 改名。编译需要 HakiOS 的 `xnu-env.sh` / Theos 工具链；`PREBUILT=1` 是上游明确提供的已有用户态程序模式。

**精确重建的边界：** 上述 revision 是当前保留 HakiOS 工作树的来源，已核对相关路径无本地改动；未找到足以证明历史基础 APFS 的全部构建参数、预编译 stage0 和外部可选内容的独立构建 receipt。因此这条命令提供真实的介质生成入口，但尚不能承诺它在全新机器上生成下述历史基础哈希。后续严格重放会在基础哈希不符时停止，不会将近似结果标为已复现。

## 2. 历史转换链

历史基础 `system.apfs` 为 `2,476,732,416` 字节，SHA256：

```text
e221581fa98e73bab8e198f9d2aea22411a852df1f4d9c8d83aa49450e7381f9
```

保留记录表明，它由 r7 / r16 等历史包继承进入后续开发树。完整链路为：

```text
system.apfs
→ system-spaceman-repaired.apfs
→ system-resource-maps-u10.apfs
→ system-launch-services-u12.apfs
→ system-cryptex-links-u13.apfs
→ system-chrono-services-u26.apfs
→ system-activation-service-u33.apfs
→ system-on-demand-u35.apfs
→ system-on-demand-u36.apfs
→ system-core-policy-u37.apfs
→ system-host-input-u59.apfs
→ system-host-input-u80.apfs
```

[`replay-plan.json`](../recipes/u80-root/replay-plan.json) 列出每一步的完整命令参数、输入 / 输出哈希和大小。它从保留 receipt 的 service label、on-demand / core-autostart / stderr 配置生成；[`receipts`](../recipes/u80-root/receipts) 保留各阶段记录。u10 的逐块长日志只保留汇总与输入输出 pin。

[`recipes/u80-root/scripts`](../recipes/u80-root/scripts) 是历史转换脚本的独立副本，仅调整依赖路径，让它们不再要求开发者的 Windows 目录布局。逻辑未改，逐文件原始 / 副本哈希见 [`script-path-adjustments.json`](../recipes/u80-root/script-path-adjustments.json)。APFS Python 工具和固定版本的 `launchd-on-demand.py` 一并附上。

## 3. 准备辅助程序与本地配置

下载 [构建依赖 Release](https://github.com/chenmingjie1/UniXNU-odin/releases/tag/build-inputs-ios16.5-xnu8796-20261107) 中的 `u80-root-replay-support.tar.gz`，先按 [构建输入说明](BUILD-INPUTS.md) 校验，再从仓库根目录运行：

```bash
tar -xzf /path/to/u80-root-replay-support.tar.gz -C recipes/u80-root
mkdir -p recipes/u80-root/inputs/rootfs/System/Library/LaunchDaemons
cp -a /path/to/hakios/sysimage/rootfs/System/Library/LaunchDaemons/. \
  recipes/u80-root/inputs/rootfs/System/Library/LaunchDaemons/
```

该小包提供历史 `build/host-virtual-input-u59/host_swipe`、`build/host-virtual-input-u80/host_swipe`、相应源码 / tbd / 编译命令 / 签名审计，以及 `full-development-trust-u39.bundle`。trust bundle 是 development 哈希列表，不含签名私钥。所有文件的哈希在包内 `manifest.json`；来源源码也可在线浏览 [`helpers`](../recipes/u80-root/helpers)。

u59 与 u80 使用的辅助程序源码不同，不应直接拿当前 `host-input/sb_ui_unlock.c` 代替历史输入。若自行重新编译，使用各目录 `build.json` 的完整命令，以自己的路径替换当中的目录。其工具链为 `clang-18` / `ld64.lld-18`，目标 `arm64-apple-ios16.5`，链接含 `-adhoc_codesign -dylib -install_name /redwood/host-input/libodin-ui-unlock.dylib`。重新构建后先审计签名及 SHA256；不同输出不能沿用历史 trust 或冒充同哈希重建。

## 4. 打印计划和严格执行

Python 3.11 或更新版本。从仓库根目录打印完整计划，不生成镜像：

```bash
python3 recipes/u80-root/replay.py \
  --base /path/to/historical/system.apfs \
  --kernel /path/to/original-20F66-kernel.macho
```

确认所有输入已就绪后加 `--run` 执行。`--kernel` 必须是从同一 IPSW 的 `kernelcache.release.iphone10b` 解包、解压并选出 arm64 slice 后的原始 `20F66` 内核 Mach-O，历史 SHA256 为 `556b35cd9014a8651e91b7295809d5d449dc7ca4ea8bf798bbf3f63a77f1cd07`。u10 脚本会检查虚拟地址 `0xfffffff004403d58` 的 50 字节模板，不能传入 IMG4 容器或自行编译内核代替。

如果已经持有哈希正确的 u37，可只重放末两级：

```bash
python3 recipes/u80-root/replay.py --start u59 \
  --base /path/to/system-core-policy-u37.apfs --run
```

u37 输入 SHA256 为 `a32c3734376145828c63b63fe2701cbd6e8a7e0f9ce39adba1b263b31fc77666`。脚本在每一级核对完整输入 / 输出哈希，拒绝覆盖既有结果；输出位于 `recipes/u80-root/build/root-media/`。完整链保存多个约 2.5 GB 中间文件，还生成 spool / unrepaired 文件，应预留足够空间。

u59 在 u37 基础上加入辅助库及 SpringBoard 的 `DYLD_INSERT_LIBRARIES` 配置并更新 development trust。u80 在 u59 基础上只替换 `/redwood/host-input/libodin-ui-unlock.dylib`，核对路径集合和其他文件的 stored payload 不变，再加入新库 CodeDirectory 的 cdhash，生成配套 trust。

## 5. 最终文件与启动配置

| 文件 | 大小 / SHA256 |
| --- | --- |
| `system-host-input-u80.apfs` | `2,478,948,352` 字节；`794454a49937b2073ccef8a77af396d3ec20ac2089ebb6fa48af09b0555e962e` |
| `host-input-development-trust-u80.bundle` | `470b02f3596768ac02f74ba4ea2ad10a271bbfb5d91858d499062edc7950b600` |
| u80 `host_swipe` 辅助库 | `1f16b919048619edcc311775a669db5b1845736a106318ff8a5a13a11ae2900e` |

将生成的 System 与匹配的 development trust 一起传入本项目 RAM 介质 / payload 准备流程；Data 介质是单独输入。不要把 APFS、trust 和内核随意跨版本混配。u88 的 [`prepare_ui_policy_root_u88.py`](../scripts/prepare_ui_policy_root_u88.py) 进一步从 u80 替换 UI 库并生成 u88 trust，运行配置见 [`u88-unixnu.toml`](../configs/runtime/u88-unixnu.toml) 和 [u85～u88 构建说明](BUILD-U85-U88.md)。

本次验证包括归档完整性、辅助程序与历史记录哈希、11 级输入输出 pin 连贯性、生成计划和脚本依赖路径；并在隔离目录实际重放了 **u59 → u80**，生成的 APFS 与 trust bundle 均匹配历史 SHA256，45,519 个其他文件的 stored payload 保持一致。见 [隔离重放结果](../recipes/u80-root/validation/u80-isolated-replay.json)。尚未执行从 Apple 下载开始的全链重建，也没有据此新增实机验收结论。

上游来源：HakiOS `oosexgang/hackios-xnu-kernel@88513176b1e96ecf0b764cd62c6f4e6ac71345e3`；core launch policy 来自 `bangprovn/ios-fuxi@27f6a31c8b27c6f9127f9cf27092968422579ccf`，文件 SHA256 `70654391de0b31d3da70dd5db57625dfc7d518fda303982225475f0b758c3a0c`。快照保留各自版权、许可和原注释；本页不改变上游文件的许可。
