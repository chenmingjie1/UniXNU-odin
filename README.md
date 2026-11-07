# UniXNU · 小米 MIX 4（odin）移植项目

将 UniXNU / XNU 内核与 iOS 用户态适配到 **小米 MIX 4（代号 `odin`）** 的实验性开发项目。目标硬件为 **Snapdragon 888 / SM8350、Adreno 660**，当前适配系统为 **iOS 16.5（20F66）**。

本仓库公开移植源码、驱动、构建脚本与开发记录，供研究、复现和协作使用。**当前为开发源码快照，尚未形成可日常使用的系统、完整的一键构建流程或受支持的永久刷入方案。**

> **构建资料补充（2026-11-07）：** 已公开 [u85～u88 实际构建流程与配置答疑](docs/BUILD-U85-U88.md)，包含 iOS 16.5 profile、Clang 编译记录包装器、实际归档链接脚本、u88 完整启动参数及 CoreCrypto seal 顺序。

> **依赖文件补充（2026-11-07）：** 已上传 [SDK 与完整 IIG 缓存 Release](https://github.com/chenmingjie1/UniXNU-odin/releases/tag/build-inputs-ios16.5-xnu8796-20261107)，含 `libcc_kext.a`、`libfirehose_kernel.a`、`native8796/generated` 和 `legacy-headers`。参见 [下载与安装](docs/BUILD-INPUTS.md) 及 [u80 APFS 获取、生成与配置](docs/SYSTEM-HOST-INPUT-U80.md)。

> **完整桌面运行包（2026-11-07）：** 已提供固定 u88 的内核、core7 驻留启动固件、ADT、System / 测试 Data / trust 和 USB 供盘工具。[下载运行包](https://github.com/chenmingjie1/UniXNU-odin/releases/tag/desktop-u88-runtime-20261107) · [中文启动说明](docs/DESKTOP-U88-RUNTIME.md)。适用于 MIX 4 / odin；其他设备未经验证，u88 底部 Home 手势和桌面 GPU 合成仍有已知限制。

## 项目情况

| 项目 | 当前情况 |
| --- | --- |
| 目标设备 | 小米 MIX 4 / `odin`；其他机型未经本项目验证 |
| SoC / GPU | Qualcomm SM8350 / Adreno 660 |
| 目标系统 | iOS 16.5，构建号 `20F66` |
| 默认分支 | [`main`](https://github.com/chenmingjie1/UniXNU-odin/tree/main) |
| 最新已记录实机版本 | u91，2026-11-07 |
| 测试方式 | 临时 RAM 启动，System / Data 介质位于内存中 |
| 源码范围 | 板级适配、显示与触摸驱动、实验性 GPU 后端、固件衔接及开发工具 |
| 发布范围 | 源码、SDK / IIG，以及独立 Release 中的 u88 完整 RAM 桌面运行文件；不含个人手机备份、已登录账号或私钥 |

本项目与参考仓库 [HakiOS / raphael](https://github.com/HeliumStudio-Dev/hackios-xnu-kernel) 的目标设备和实现路径不同。该仓库的 Redmi K20 Pro / Mi 9T Pro 启动包、GPU / Wi-Fi 结论及操作步骤，不能直接作为 MIX 4 的测试结果或使用说明。

## 最近实测与功能进度

以下结论包含 **u89 交互反馈与 u90～u91 GPU 实机结果**。编译、模拟器运行和主机测试，需要与实机验证分开看待。

| 模块 | 已观察到的结果 | 当前限制与后续工作 |
| --- | --- | --- |
| 内核与桌面 | UniXNU 源码内核能够在实机显示 SpringBoard 桌面 | 稳定性与完整构建流程仍需完善 |
| 显示 | 已接入原版 iOS 16 帧缓冲接口，由 CPU 复制到屏幕扫描输出缓冲区 | 仍需优化性能；早期版本报告过间歇性显示异常 |
| 触摸 | ST SALIXP `0x3640` 触摸屏能够产生真实点击和滚动输入 | 滑动非常缓慢，底部边缘与 Home 手势尚未验证通过 |
| 自动锁屏策略 | 调整启动顺序后，原版 SpringBoard 防空闲锁屏断言可在自动锁屏前生效 | 当前是开发阶段处理方式，正常锁屏与休眠仍需适配 |
| Adreno 660 | GPU 后端初始化与离屏像素自测已通过 | **尚未实现或验证桌面 GPU 合成加速** |
| 原版 IOSurface 导入适配库 | u91 实机通过 16KB 表面导入、GPU 命令、fence 完成及 4096 字全量回读，零错误 | 当前仅为内存写入探针，尚未接入桌面绘图前端 |
| 存储 | System / Data 通过 RAM 介质运行 | 不提供持久化 iOS 安装方案 |

u89 修正防锁屏断言的请求时机后，实机点击恢复；随后一次上滑出现黑屏、白色转圈并回到桌面。采样记录显示 `backboardd` 和 `SpringBoard` 进程均发生替换，**这属于进程重启现象，不能视为 Home 手势成功**。目前没有捕获到足以确认根因的退出原因或完整崩溃堆栈。

当前桌面仍使用 CPU 复制显示路径。GPU 初始化成功、离屏像素验证成功、IOSurface 适配库编译成功，都不能单独证明桌面已经获得 GPU 加速；复制耗时也不能直接换算成滚动帧率或触摸延迟。

u90 的原版表面探针曾被 GPU 服务访问检查拒绝。经用户明确授权，u91 为该服务的 SpringBoard／backboardd 访问加入限定的开发沙箱例外，随后通过导入与回读。桌面依然使用 CPU 合成与复制；参考仓库的 Mesa／EAGL 前端尚未安装。详见 [实机状态与证据](docs/STATUS.md)、[桌面 GPU 接入进度](docs/GPU-INTEGRATION.md) 和 [Helium GLES 路径核对](docs/HELIUM-GLES-REFERENCE.md)。

## 源码目录

| 路径 | 用途 |
| --- | --- |
| `drivers/OdinStTouch`、`package/OdinStTouch` | 原生 HID 设备、ST 初始化、FIFO 解析与触摸报告桥接 |
| `drivers/OdinDisplay` | 原版 iOS 16 帧缓冲接口与 CPU 扫描输出复制路径 |
| `drivers/OdinAdreno` | 实验性 A660 后端、运行计数器与线程采样 |
| `firmware` | 板级显示 / 电源衔接、驻留 USB 控制与诊断 |
| `host-input` | 开发辅助程序、防空闲锁屏断言与 IOSurface 导入适配 |
| `patches`、`configs`、`dts`、`soc` | 内核补丁、构建配置、设备树与 SoC 适配输入 |
| `scripts` | 分阶段构建、ABI 审计、打包与状态采集工具 |
| `recipes` | 从生成目录中整理保留的源码构建配方 |
| `docs` | 当前状态、构建依赖、GPU 接入说明及历史记录 |

## 获取源码与构建准备

```bash
git clone --branch main https://github.com/chenmingjie1/UniXNU-odin.git
cd UniXNU-odin
```

**克隆完成不代表可以直接生成启动镜像。** 当前脚本描述的是既有 Windows + Linux 构建虚拟机开发环境，部分步骤依赖早期生成文件、本地 SDK、精确版本的 ABI 审计结果及未随仓库分发的介质。

开始复现前，请先阅读 [构建输入说明](docs/BUILD.md)，并准备：

1. [`source-pins.json`](source-pins.json) 固定的 UniXNU 与组件源码版本。
2. 匹配的 XNU 源码、补丁、编译器、SDK 头文件，以及原版 iOS 16.5 / `20F66` 接口审计输入。
3. 单独取得的 System / Data 介质、原版驱动和本机固件输入；这些内容不随源码发布。
4. 脚本所需的 Linux 构建环境、历史编译记录及显示 / 存储 / HID ABI 生成文件。
5. 与本地路径匹配的 Windows 打包工具、EDK2 与 LLVM 环境。

`board.toml` 描述的是早期仅核心功能的板级选择，不能当作完整 u89 构建清单。缺失的 ABI 数据必须从精确匹配的原版接口推导和审计，不能用猜测的偏移或其他 iOS 版本的数据替代。

## 主机检查与实机验证

准备好 Python 和支持相应目标的 Clang 后，可运行触摸报告桥接检查，将下面的 Clang 路径替换为本机实际路径：

```bash
python scripts/check_touch_bridge.py --cc /path/to/clang --clang /path/to/clang
```

这项检查验证协议与触摸报告桥接逻辑，不证明实机 Home 手势、滚动性能或桌面 GPU 渲染已经可用。

当前实机验证基于临时 RAM 启动。使用已构建文件可按 [u88 完整运行包教程](docs/DESKTOP-U88-RUNTIME.md) 下载、校验并启动；从源码重建全部相同文件的闭环仍未完成。本项目不提供永久刷入步骤。

## 常见问题

**能否直接下载后刷入，作为日常系统使用？**

可以下载 u88 运行包做临时 RAM 桌面启动，但它仍有已知功能限制，不是可日常使用或永久刷入的发行版。

**现在是否已经有桌面 GPU 加速？**

尚未验证。A660 后端离屏自测已经通过，但桌面 Metal 前端、原版 IOSurface 同步和最终显示链路仍需接入与实机验收。

**为什么能点击，却仍不能正常上滑返回？**

触摸报告被系统接收不等于 Home 边缘识别通过。u89 已加入精确匹配 `20F66` 的边缘元数据候选实现，但实机尚未通过 Home 手势验证，并出现过 UI 进程重启，根因仍需调查。

**为什么仓库里的旧记录与当前状态不同？**

`docs/history` 保留了历史阶段记录。判断当前功能时，应以本页标注的版本及对应实机证据为准，并核对测试使用的内核与介质哈希。

## 问题反馈

请通过 [Issues](https://github.com/chenmingjie1/UniXNU-odin/issues) 提供设备代号、Git 提交号、测试版本、内核 / 启动镜像哈希、启动参数、复现步骤，以及对应的实机现象和诊断记录。请区分编译结果、主机测试结果与真实设备操作结果。

公开日志或截图前请移除账号、设备标识和其他个人数据；不要提交密钥、凭据、完整 Apple 系统介质或厂商固件数据。

## 许可与致谢

本仓库包含多种许可证下的组件，以各文件头、组件许可证与 [源码许可说明](SOURCE-NOTICE.md) 为准，不为全部文件统一声明一种许可证。

- ST 触摸相关代码保留 `GPL-2.0-only` 声明及 Xiaomi MiCode 来源说明。
- 显示与 RAM 块设备等组件保留各自许可证。
- HakiOS 衍生用户态代码保留原有署名与 MIT 许可；该许可不改变 XNU 修改的许可。
- XNU 修改继续遵循原有 Apple Public Source License 声明及适用的上游条款。
- u89 边缘触摸设计参考固定版本的 `OddlyLabs/unixnu-fuxi`；针对 `20F66` 的表大小、槽位和字段经过独立核对，未复用其 iPadOS 偏移。

感谢 UniXNU、HakiOS、Project Silicium / Mu-Silicium、Xiaomi MiCode 及相关上游项目的贡献者。上游版本与来源见 [`source-pins.json`](source-pins.json) 和 [源码许可说明](SOURCE-NOTICE.md)。
