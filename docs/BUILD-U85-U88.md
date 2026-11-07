# u85～u88 构建与配置公开说明

本文回应 u85 / u88 源码内核的构建命令、系统 profile、编译记录、平台驱动、帧缓冲检查、启动参数及 CoreCrypto seal 顺序。依据是保留的构建脚本、编译记录、打包清单和实机采集结果，不把后续代码当成这两个版本已验证的实现。

## 1. 实际构建路径与版本

u85～u88 使用的是 **Linux 构建虚拟机中的离线 Make 编译 + 显式归档链接 + 原版驱动预链接**，不是单独运行 `unixnu build kernel -D .` 得到完整实机内核。

XNU 基线是 **8796.101.5**，Git revision `aca3beaa3dfbd42498b42c5e5ce20a938e6554e5`。u85 与 u88 的最终预链接内核相同：

```text
3f95a57bbd346cf8a8c493d365cd98299ce17d21255fa3f5400c133f72bd9d1b
```

u88 更新的是 RAM System 中的签名 UI 辅助程序及配套 trust bundle，没有更换这份内核。具体输入文件大小与哈希见 [`configs/runtime/u85-u88-artifacts.json`](../configs/runtime/u85-u88-artifacts.json)。

本次把构建虚拟机中的关键脚本保存在 [`recipes/u85-u88`](../recipes/u85-u88/README.md)。`guest/` 下的文件保留原有绝对路径，以便审阅真实流程；把它们当成全新机器可直接运行的安装包，会缺少 SDK、组件源码、历史生成文件和本地介质。

### 构建环境与编译记录

原构建根目录为 `/home/odin/unixnu-odin-build`，其中 `upstream/` 是 UniXNU 工作树。离线入口为：

```bash
cd /home/odin/unixnu-odin-build
bash build_offline_kernel.sh
```

其完整 Make 参数见 [实际 `build_offline_kernel.sh`](../recipes/u85-u88/guest/build_offline_kernel.sh)。关键项包括：

```text
SDKROOT=iphoneos
ARCH_CONFIGS=ARM64
MACHINE_CONFIGS=BCM2837
KERNEL_CONFIGS=DEVELOPMENT
RC_DARWIN_KERNEL_VERSION=22.5.0
RC_ProjectSourceVersion=8796.101.5
CC=/home/odin/unixnu-odin-build/record-clang
CXX=/home/odin/unixnu-odin-build/record-clang++
OBJROOT=/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj
```

`BCM2837` 是沿用的构建目标名，不表示手机是该 SoC。真正的板级平台与 CPU 由适配组件提供。

第一次编译用于生成真实目标文件和编译记录。缺少最终 provider archives 时链接可能失败，这类结果不能部署；必须检查日志确认失败发生在哪一步，不能把任意失败都当成正常的“bootstrap 成功”。

### 组件归档与最终链接

构建顺序是：生成 XNU 编译记录 → 构建实际 provider / 驱动归档 → 注册板级 owner → 最终链接 → seal → 原版驱动预链接与审计。

在相应源代码、SDK、ABI 输入与环境已经准备好的原构建树中，平台归档的入口为：

```bash
export UNIXNU_XNU_ARCH=arm64
export UNIXNU_IOS_VERSION=16.5
python3 upstream/scripts/build-arm-driver.py ArmDTPlatform
python3 upstream/scripts/build-arm-driver.py ArmCpu
```

CoreCrypto 与 pthread 的本地归档导入入口是：

```bash
python3 build_crypto_archive_import.py
python3 build_crypto_archive_import.py --namespace
python3 build_pthread_archive_import.py
```

这两个 import 脚本会核对本地源码文件全集与逐文件哈希；源码需要按对应公开来源和 receipt 单独准备，脚本不会凭空下载并填齐它们。

u85 GPU 阶段的实际入口为：

```bash
python3 evidence/odin-gpu-u85/compile_gpu_guest.py
python3 evidence/odin-gpu-u85/link_gpu_guest.py
```

该阶段仍要求已具备 u75 触摸归档、u73 平台电源归档、u82 显示归档、RAM 块设备，以及相应测量过的原版接口输入。`link_gpu_guest.py` 负责临时接入 `odin_gpu_owner_start()`、构建 GPU archive，并从 u75 链接脚本生成 u85 最终链接脚本；仅手动增加一个 `.a` 不等价于完成 owner 接入。

实际最终 [u85 `link_kernel.sh`](../recipes/u85-u88/guest/evidence/odin-gpu-u85/link_kernel.sh) 明确链接：

```text
evidence/odin-gpu-u85/libOdinAdreno.a             force_load
evidence/odin-touch-u75/libOdinStTouch.a          force_load
evidence/odin-pmgr-u73/libOdinPlatformPower.a      force_load
evidence/odin-display-owner-u82/libOdinDisplay.a  force_load
upstream/build/corecrypto-2023/libcorecrypto_kernel_noasm-namespaced.a
upstream/build/armdt-platform/libArmDTPlatform.a force_load
upstream/build/armcpu/libArmCpu.a                force_load
upstream/build/libpthread-kernel/libpthread_kernel.a force_load
upstream/build/ram-block/libRamBlock.a           force_load
```

还包括 SDK 的 `firehose_kernel` 和通过 `LD_KERNEL_LIBS` 传入的 `libcc_kext.a`。所有链接参数和对象级宏以该脚本全文为准；仓库原先的 `scripts/link_offline_kernel.sh` 是更早阶段的基础配方，不能独立代表 u85 完整链接闭包。

Windows 侧既有编排入口为 `scripts/build_odin_gpu_u85.py`。它调用虚拟机编译 / 链接后，运行：

```bash
python scripts/prepare_ios16_prelink.py \
  --kernel build/gpu-port-u85/native-real-iig.macho \
  --output-dir build/gpu-port-u85 \
  --driver-policy configs/original-driver-policy.toml
python scripts/audit_ios16_prelink.py --input-dir build/gpu-port-u85
```

这些是开发配方的实际入口，不能替代其输入准备。仍缺失哪些输入，见本文末尾。

## 2. iOS 16.5 profile、prelink roots 与 RAM root

实际 Linux 工作树中的 profile 已公开为 [`profiles/os/ios-16.5-20F66/profile.toml`](../profiles/os/ios-16.5-20F66/profile.toml)，包含 `[ipsw]`、`[kernel.prelink]`、`[payload]` 与 `[adt]`。

**该文件没有 `[root]` 段。** 当前流程通过单独的 APFS / RAM 介质准备脚本和 payload sidecar 传入 System、Data、trustcache；不能从不存在的配置段推导完整用户态。

还需区分两份 profile 的用途：

| 文件 / 实现 | 实际用途 |
| --- | --- |
| `profiles/os/ios-16.5-20F66/profile.toml` | 虚拟机 UniXNU 工作树保留的 OS profile |
| `recipes/u85-u88/reference-nx769j/os-profiles/ios-16.5-20F66/profile.toml` | `prepare_ios16_prelink.py` 实际读取的固定版本参考 profile |
| `scripts/prepare_ios16_prelink.py` | 校验精确 kernelcache，使用参考 roots，并补入实际 XML / IDREF 解析确认存在的 `com.apple.iokit.IOHIDEventDriver` |
| `recipes/u85-u88/evidence/u85-prelink-attempt.json` | 实际传入的最终 roots、slide 和产物哈希 |

因此，不能只拿 Linux profile 的历史 `tool = "scripts/emit-prelink-nx769j.py"` 字段，就断言整个构建经过统一 CLI。真实调用链是板级 `prepare_ios16_prelink.py`、固定版本 XnuPrelink 工具及参考 wrapper 的 literal-pool 校验。原版 executable kext 保持完整，仅按 `configs/original-driver-policy.toml` 选择禁用特定硬件 personality。

u88 RAM System 的入口是 `scripts/prepare_ui_policy_root_u88.py`：读取此前准备的 `system-host-input-u80.apfs`，替换签名 UI 辅助库，生成新的 System 文件和 development trust bundle。Data 介质由历史 RAM fixture 继承。最终打包布局和哈希已经单独公开，原版介质需自行取得。

## 3. XNU 8796 没有内置 `-MJ`，编译记录如何生成？

确实不依赖 XNU 8796 的 `makedefs/MakeInc.rule` 内置 `-MJ`。实际使用的是上文 `CC` / `CXX` 指向的 [record-clang](../recipes/u85-u88/guest/record-clang) 与 [record-clang++](../recipes/u85-u88/guest/record-clang++) 包装器，而不是 `scripts/record_kernel_compile.sh`。

- 编译参数包含 `-c` 与 `-o output` 时，包装器追加 `-MJ output.json`。
- C 规则缺少显式 `-o` 时，`record-clang` 从 `.c` 文件名推导 `.o`，追加 `-o` 和对应 `-MJ`。
- `record-clang++` 的保留版本只处理已有显式 `-o` 的编译；不能把两份 wrapper 的能力混为一谈。
- 最后调用实际的 `xnu-clang` / `xnu-clang++`，需要使用能接受该选项的 Clang。

`build-arm-driver.py` 从 `IOPlatformExpert.cpo.json` 读取真实源内核 C++ 编译命令，再替换源文件与输出路径。记录名就是：

```text
upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json
```

[公开的编译记录](../recipes/u85-u88/compile-records/IOPlatformExpert.cpo.json) 保留 Clang 的原始输出格式；某些文件末尾有逗号，读取时使用 `json.loads(text.strip().rstrip(','))`。这些当前工作树记录可说明编译参数接口；它们采集于本次公开时，不是每个对象都已证明为 u85 当日不可变快照。u85 目录中保留的专用命令记录另有单独文件。

## 4. ArmDTPlatform 与 ArmCpu 是否需要？

**本项目 u85～u88 路径需要二者。** 实际链接脚本对它们使用 `-Wl,-force_load`，不是仅把组件名写在 `board.toml` 中。

`patches/xnu/armvirt-platform-personality.patch` 在内核 personality 表注册 `ArmDTPlatform`、`ArmCpu`，并保留低优先级 `IOPanicPlatform` fallback。`configs/original-driver-policy.toml` 则禁用原版 AppleARMPE / AppleARMCPU 的硬件匹配，让本项目平台与 CPU provider 接管板级设备。

省略归档或破坏 personality 闭包会失去该实现所依赖的平台匹配；具体表现可能是链接缺失符号或运行期无法匹配。不能把“必定在某一行落到 IOPanicPlatform”当成所有删减组合都已经实测的结论。不能通过删除 panic fallback 来代替平台适配。

## 5. `0xea600000 / 4320 / 1080 / 2400 / 32` 的依据

这组值是**当前保留开发环境的帧缓冲布局约束**，不是对所有 MIX 4 固件版本永久成立的硬件常量：

| 项目 | 值 |
| --- | --- |
| 物理基址 | `0xea600000` |
| 每行字节数 | `4320` |
| 宽 / 高 | `1080 × 2400` |
| 像素位深 | `32` |
| 实际画面字节数 | `10,368,000` |
| 早期映射窗口 | `[0xea600000, 0xeb000000)`，五个 2 MiB 块 |

公开了 [布局与证据范围](../recipes/u85-u88/evidence/framebuffer-layout.json) 和 [u88 USB 实机几何回读](../recipes/u85-u88/evidence/u88-framebuffer.txt)。USB 回应提供宽高、rowBytes 和大小，**不包含物理基址**；物理基址约束来自保留的 MMU 诊断安装脚本 / 补丁，不能把几何回读伪称为新的基址实测 dump。

当前没有已验证的“只校验宽高 / rowBytes、不校验基址”的宽松版本。本补丁后续直接按固定起止地址修改早期页表，仅删去基址比较会让检查与实际映射不一致。若要支持其他布局，必须一并处理真实范围、对齐、溢出、已有映射及可用页表池，然后重新验证；本次公开不修改这段运行代码。

## 6. u88 的完整启动参数

完整配置已公开为 [`configs/runtime/u88-unixnu.toml`](../configs/runtime/u88-unixnu.toml)：

```text
-v serial=0 cpus=1 rd=md0 odin-init-path=/sbin/launchd.ios dyld_flags=8 odin-data-mount=1 odin-gop-display=1 odin-gop-ready=1 odin-gop-pm=1 odin-gop-cpu=1 odin-gop-dirty=1 odin-key-events=1 odin-sb-ui=1 odin-sb-pathvars=1 odin-surface-inspect=1 odin-key-state=1 odin-ui-sample=1 odin-touch=1 odin-touch-bus=1 odin-gpu=1 odin-gpu-selftest=1
```

`source-pins.json` 中 `legacy_runtime.cmdline` 的 `bootcpu=7 cpus=1 … gpu=1` 是**旧 HakiOS 运行基线**，不是 u88 源码内核这条参数。u88 使用 `odin-gpu` 命名，`cpus=1` 表示单 CPU；“core7 驻留启动”的固件交接信息也不能直接改写成旧内核的 `bootcpu` 参数。

离线 QEMU 验证可能使用另外一条诊断参数，以各次 verification 记录为准，不能替换实机 `unixnu.toml`。u85 配置同时保留在 [`u85-unixnu.toml`](../configs/runtime/u85-unixnu.toml)，便于对比。

## 7. CoreCrypto bootstrap 与 seal 的顺序

保留的离线流程避免了“还没有链接 source provider，却要求 `_source_corecrypto14_bootstrap` 已存在”的循环：

1. `build_offline_kernel.sh` **直接调用 XNU Make**，启用 `XNU_SOURCE_CORECRYPTO14=1`，生成真实对象和记录。它没有在末尾调用 seal。
2. 基于这些记录构建 CoreCrypto provider 与 namespaced archive，以及其他平台 / 驱动归档。
3. u85 `link_kernel.sh` 把归档传入 `LD_KERNEL_ARCHIVES` 后，重新调用离线 Make 完成真正的内核链接。
4. 该链接脚本随后才运行 `upstream/scripts/seal-source-crypto-kernel.py`。保存的 [seal 日志](../recipes/u85-u88/evidence/u85-kernel-crypto-seal.txt) 只说明构建期 POST integrity field 已填充；它本身不证明运行期自测通过。

没有删除 seal 中 `_source_corecrypto14_bootstrap` 的校验，也不把缺少 provider 的结果伪装成成功。

如果改走上游 `build-xnu-4k-baseline.sh`，其末尾在 source 模式会自动 seal；没有 provider 的前置阶段就会出现问题。该脚本的 mode 变量是 `XNU_CRYPTO_BOOTSTRAP`；简单设置另一个名为 `CRYPTO_BOOTSTRAP` 的环境变量，不等于改变离线脚本。这里保存 [上游工具快照](../recipes/u85-u88/upstream-tools/build-xnu-4k-baseline.sh) 供核对，**不是声称 u85 的编译由它驱动**。`prelinked` 模式还会改变 `prng_random.o` 的 provider 入口选择，不能仅为绕过 seal 把它与 source 模式混用。

## 公开范围与尚未补齐的复现输入

已公开：本页涉及的 profile、实际 Make / 链接脚本、Clang 包装器、关键编译命令、CoreCrypto / pthread import receipt、prelink roots、运行配置、介质哈希和帧缓冲约束。


系统与原版驱动介质、厂商固件数据、其他历史 ABI 生成输入，以及相应阶段的 provider 编译产物仍须按流程单独取得或重新生成。SDK / IIG 附件并未补齐其余全部依赖。

这次没有重新构建完整内核，也没有从全新环境验证生成 u85 相同哈希。公开真实记录可以消除上述配置猜测，但目前仍不能承诺 fresh clone 的端到端独立复现。源码与工具的许可证 / 来源见 [`recipes/u85-u88/README.md`](../recipes/u85-u88/README.md) 和 [SOURCE-NOTICE.md](../SOURCE-NOTICE.md)。
