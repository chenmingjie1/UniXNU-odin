# MIX 4 u88 桌面运行包

这套运行包提供同一组保留实测输入：Android 临时 RAM 启动镜像、core7 驻留 DarwinBoot、预链接内核、ADT、System、测试 Data、development trust 和启动配置。下载后无需先构建 SDK 或 IIG。

**适用设备：小米 MIX 4，代号 `odin`。** 它保留 u88 的桌面及触摸操作记录；其他设备和其他固件环境尚未验证。u88 滚动仍慢，底部 Home 手势未通过，桌面 GPU 合成未实现。它是固定开发运行包。

[下载 u88 运行包 Release](https://github.com/chenmingjie1/UniXNU-odin/releases/tag/desktop-u88-runtime-20261107)

## 1. 下载完整运行环境

Windows、Linux 或 macOS 安装 Python 3.11 或更新版本。另安装 Google [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，把 `adb` / `fastboot` 加入 PATH；Windows 需要正确的 Android bootloader USB 驱动。

从 Release 下载并解压 **`u88-launcher.zip`**，在解压目录运行：

```bash
python fetch_u88_runtime.py --output u88-runtime
```

也可以从本仓库执行：

```bash
python scripts/fetch_u88_runtime.py --output u88-runtime
```

工具会下载内核 / 固件核心包和 System / Data 分卷，逐个验证 SHA256，并在本地还原完整文件。网络中断可重新运行；已校验文件会复用，未完成分卷支持断点续传。总下载量约 2.5 GB，解压与缓存共需约 6 GB 空间。不要手工更改分卷顺序或把其他版本文件放进目录。

## 2. 先做离线检查

```bash
python u88-runtime/scripts/boot_u88_runtime.py --runtime u88-runtime --verify-only
```

应输出 `All u88 runtime files match. No device commands executed.`。检查涵盖完整内核、System、Data、trust、ADT、DarwinBoot、配置和 Android boot 镜像。出现哈希错误就停止，先重新取得完整文件。

## 3. 让自己的 MIX 4 进入 fastboot

设备需要已解锁 bootloader。连接后确定自己的序列号：

```bash
adb devices
adb -s YOUR_SERIAL reboot bootloader
fastboot devices
```

将 `YOUR_SERIAL` 替换为你设备的值。启动工具会再次检查 fastboot `product=odin` 和 `unlocked=yes`；不再使用开发者设备的序列号。

## 4. 临时启动并供应 System / Data

```bash
python u88-runtime/scripts/boot_u88_runtime.py --runtime u88-runtime --boot --serial YOUR_SERIAL
```

使用特定 fastboot 路径时追加 `--fastboot /path/to/fastboot`，Windows 可填 `C:\platform-tools\fastboot.exe`。

保持 USB 连接并让命令继续运行。工具会先用 `fastboot boot` 加载约 2 MB 的固件启动镜像，再向固件提供七个固定文件，包括约 2.48 GB 的 System 和约 505 MB 的 Data。**只启动小 boot.img 然后关闭供盘程序，无法得到完整桌面。** 具体传输时间取决于 USB 环境。

内核到达 post-VM 阶段后，工具及时请求 u88 原版 UI idle-disable assertion，避免 UI 在交互前自动锁住。请求成功只表示启动流程完成了该阶段；是否显示并能操作 SpringBoard，仍以手机画面和操作为准。

该命令执行临时 RAM 启动与本机 USB 供盘，不执行 flash、erase、format 或分区写入。需要回 Android 时可强制重启设备；没有持久化 iOS 安装。

## 5. 文件必须成套

```text
u88-runtime/
  runtime-manifest.json
  boot/MIX4-UniXNU-desktop-u88-boot.img
  esp/EFI/UniXNU/
    DarwinBoot.efi
    unixnu.toml
    Payloads/
      kernel.macho
      kernel.macho.adt
      kernel.macho.system
      kernel.macho.data
      kernel.macho.trustcache
  scripts/boot_u88_runtime.py
```

完整字节数与 SHA256 见 [`u88-runtime-manifest.json`](../configs/runtime/u88-runtime-manifest.json)。该启动方式由固件驻留 core0，内核通过板级 PSCI 路径运行在 core7。不能用通用 UniXNU 菜单、旧版 DarwinBoot 或只有 `-v serial=5` 的配置替代本套固件和供盘流程。

System 是 u88 的版本，已经在 u80 基础上替换签名 UI 辅助库；配套 trust 也随之改变。Data 是离线 QEMU 初始化的测试状态，无登录账号、凭据或钥匙串条目；包含自动生成的系统 UUID、系统数据库和日志，不是个人手机备份。运行时 Data 位于私有 RAM 副本中。

## 6. 出现故障时提供什么

每次运行会生成 `u88-runtime/runs/时间/events.jsonl`。请提供该文件、手机照片、设备固件版本和完整命令；不要只提供最后的 UniXNU 菜单画面。

| 现象 | 优先核对 |
| --- | --- |
| 校验不通过 | 分卷是否齐全，是否混入其他内核 / System / trust |
| fastboot 找不到设备 | 自己的序列号、USB 驱动、是否处于 bootloader 模式 |
| 只显示 UniXNU 菜单、旧 A000 面板 | 实际使用的 boot.img 是否匹配；是否绕开了本工具，载入旧内核或默认配置 |
| `Runtime USB device missing` | `odin-unixnu-u64` 枚举、USB 连接和供盘日志 |
| post-VM 超时 | events 中的阶段与手机诊断信息；不是已经证明 SpringBoard 崩溃 |
| 出桌面后画面不动 | UI idle 请求时机、触摸状态；u88 不保证正常休眠 / 锁屏行为 |

## 验证范围

原始 u88 记录确认桌面画面和继续触摸操作。新运行包逐文件匹配这些保留输入，启动工具在主机上验证 USB 数据帧、边界、文件完整性和 UI 请求顺序。当前没有在另一台 MIX 4 上重新做实机验收，下载包也不能改变机型 / 固件适配边界。

这解决了“没有完整运行文件、依赖开发者本地目录和序列号”的发布缺口。**从 fresh clone 自行编译全部相同二进制**仍是另一项工作：历史基础 APFS 的完整构建来源、全部 ABI/provider 生成输入和固件基线的完整可重建流程尚未闭合。详见 [公开缺口清单](PUBLICATION-GAPS.md)。
