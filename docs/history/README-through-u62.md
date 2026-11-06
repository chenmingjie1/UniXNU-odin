# MIX 4 → UniXNU

**最新结果（u62）：电脑 QEMU 已实际显示 iOS16.5 图标桌面。**
截图含“设置、照片、日历”等应用图标及底部 Dock；最终日志也确认原版 UI 锁已退出。
证据：`../../outputs/MIX4-UniXNU-display-u62/runtime/periodic-frame-013.png`。
这是电脑上的 CPU 显示路径，尚未验证 MIX 4 实机的 UniXNU 桌面、触摸或 A660 GPU。
本轮没有发送任何手机命令，也没有把电脑内核标记为可刷的手机启动镜像。

以下保留诊断演进及失败证据。

u63 实机交接准备：已编译独立 `darwinboot-u63/DarwinBoot.efi`，修复原引导器
256 MiB 限制拒绝 2.48 GB 原始 System 内存盘的问题，并实现 `.system` / `.data`
只读文件分块载入同一个已分配内存窗口。不会先分配整份 System/Data 临时副本。
实际暂存的 System、Data、内核和信任缓存与 u62 电脑桌面输入逐项核对，
设备树保留实测 SM8350 GIC 和 CPU 资源，移除 QEMU 虚拟化标志。
生产 C 解析器的截断/非法范围检查、分块复制及读盘失败拒绝、13 项启动 ABI 均通过。
文件集位于 `build/device-desktop-u63`，尚缺实机 RAM 上传到 UEFI 文件服务的连接；
它不是 Android boot.img，不能以此宣称实机桌面、触摸或 GPU 已验证。

早期阻塞诊断修正：u08 实机最后一个标记在 `PE_init_platform(FALSE)` **之前**，
没有返回标记不能证明函数内部卡死。u63 使用原 u08 设备树、没有 QEMU 硬件覆盖的
电脑 CPU 回放已通过该函数及 CPU 拓扑初始化，到达 `pe_arm_init_interrupts` 入口。
这只排查了通用 CPU/设备树路径，尚未验证实机 GIC 或定位原实机故障指令。

当前电脑验证更新（u51–u53）：u51 的两种客户端都未能创建虚拟触屏服务，
没有发生上滑，也没有进入图标桌面。原始 iOS16.5 服务端的检查已定位到
`com.apple.private.hid.client.event-dispatch`；GitHub Apple IOHIDFamily 工具权限表也包含同一键。
u52 只给独立测试程序增加这一个权限，代码页与权限签名槽校验通过，
系统副本 45,519 个原文件载荷不变。u52 实测已创建并打开虚拟触屏，接收一轮 22 个上滑事件，
但画面仍为锁屏；随后原版电源管理进入整机睡眠并停在 `ArmCpu::haltCPU`。
u53 按 GitHub ios-fuxi 记录使用现有 `defaults/sleep-disabled=1`，仅改电脑 ADT，
实测没有再进入整机睡眠，但画面仍为锁屏。u54 唤醒协议未收到 TouchDetectionMode，三次上滑未改变画面；u55 属性对照也未打开按钮服务，已停止重复。
u56/u58 的独立 SBS 外部请求已实际发出，但最终日志均为一次请求、零回调，画面仍是锁屏。
已进一步核对公开回调的 BOOL 转换，修正早先错误的对象回调声明；尚未运行该外部回调修正版。
u59 按固定 GitHub HakiOS 的进程内方法制作狭窄退出锁屏组件，只改变 SpringBoard 作业的一项环境配置，
原始可执行文件和 u31 内核保持不变；最终日志没有组件构造函数记录，画面仍为锁屏。
u60 重新从 GitHub 获取固定提交 `88513176b1e96ecf0b764cd62c6f4e6ac71345e3` 的
`xnu/hakios.patch`，确认上游明确指出 launchd 会过滤作业中的 `DYLD_` 变量，
因此必须由内核 `exec_extract_strings` 加入变量并计算参数空间。
已移植为默认关闭、仅开发内核中 `odin-sb-ui=1` 对 SpringBoard 生效的固定组件交接。
新内核完成编译、30 个原始驱动代码完整性校验、338 项显示接口校验及独立线程布局导出。
u60 电脑启动日志确认环境注入执行，但最终 Data 没有组件日志，画面仍为锁屏。
u61 依据 Apple `dyld-1066.8/DyldProcessConfig.cpp` 和 HakiOS 的 `0x5a` 参数 ABI，
仅在原 AMFI 返回成功、开发测试显式开启且进程为 SpringBoard 时，增加路径变量处理位。
实测原 flags 为 `0x69`，增加 bit 1 后为 `0x6b`，随后 Data 首次出现签名组件的构造函数日志。
未采用上游的全局 `0xff` 许可替换。u61 最终日志确认三次原版方法调用，
第一次返回 1，随后两次返回 0；实际画面是密码输入页，仍不是桌面。
u62 对照同一提交的 `MiniAppleKeyStore.cpp`，修正空白 RAM 测试上下文的无密码状态：
原 `ss=4` 缺少 no-passcode bit 1，现改为 `ss=6`，同步 selector 7 返回值及 `sls=3`。
未加入任何真实密码、密钥包或密钥操作。u62 已编译校验，实际截图确认图标桌面，尚未操作手机。
u50 最终 Data 因空间不足截断，已标记无效，后续不复用。
本轮没有操作手机，尚未生成可在 MIX 4 进入桌面的新镜像。


## 当前状态（2026-11-04，电脑端）

最近达到的可见界面为 u62 的**图标桌面**，仅限电脑 QEMU；u49–u60 的锁屏结果为历史记录。
尚未生成或验证可在 MIX 4 进入 UniXNU 桌面的新手机启动镜像。
u46–u48 使用固定版本 UniXNU 原版线程快照工具，配合本机 DWARF 布局；
真实线程栈表明 LaunchServices 注册持续推进，随后 SpringBoard 越过配置检查并呈现欢迎界面。
u48 完成 1,274 帧复制/退休，无内核 panic 或签名拒绝；证据在
`../../outputs/MIX4-UniXNU-display-u48/`，其中周期截图包含实际 Hello 动画。
u49 重新通过 GitHub API 获取并固定 ios-fuxi 最新 `sweet-root-tweaks.py` 的
`9b34af2f635535fc9771ad41182fd72ed0650d8e` 版本，从 AST 提取首次设置配置，
只合入独立电脑 Data 副本。未执行下载脚本，未复制其激活状态或关闭 watchdog 的修改。
两项已有 plist 与一项新增 plist 已逐项验证；2,766 个原有路径、文件内容和元数据保留。
u49 实际显示上述锁屏，11 帧复制/退休，零映射失败、签名拒绝或内核 panic；
不能据此宣称真实设置流程完成、图标桌面或实体硬件已修复。
证据为 `../../outputs/MIX4-UniXNU-display-u49/`。
u50 采用固定版本 HakiOS `userland/src/inject.c` 的原生 iOS16.5 虚拟 HID 服务 API，
编译独立有限上滑测试程序。所需导出逐项与当前系统原始共享缓存核对，
17 个签名页全部通过；系统副本的 45,519 个原始文件内容再次核对一致。
它作为独立 launchd 作业运行，不注入原始进程或改写内核，
也不代表 MIX 4 的 ST 触摸已接入 UniXNU。其失败结果见上方 u51/u52 更新。
已参考并固定 GitHub `UniXNU/GopFramebuffer` 与 `UniXNU/UniXNU` 的实际显示实现；
源码版本及对照结果见 `research/github-display-20261104/FINDINGS.md`。
u29 实测接通原版 IOKit 电源调度，实际提交请求已进入显示验证入口。
u30 暴露待处理队列与就绪队列接错，u31 按本机原版 iOS16.5 入队指令修正后，
480 秒电脑回放实际接收、复制并由原版驱动完成 **427 帧**，复制/激活失败为零、无 panic。
这证明 CPU 帧显示路径已接通，**不证明桌面、实体 MIX 4 显示或 A660 GPU 可用**。
统一证据入口为 `../../outputs/MIX4-UniXNU-display-u31/progress.json`。

u32 已核验 55 项迁移组件/XPC 的 1,084 个原始代码页，600 秒对照不再记录签名拒绝，
完成 1,756 帧复制/退休，画面进入迁移进度条。u33 补入原版 mobileactivationd 服务，
实际断点唯一匹配到其 `main()` 的 `Migration failed.` 路径；不能据此认定唯一根因。

依据固定版本 `bangprovn/ios-fuxi` 的 `launchd-on-demand.py` 和 `mkadt.py`，
u36 发布其余原版服务并按需启动，补入模拟环境专用的六字节网络地址输入。
600 秒回放完成 1,826 帧复制/退休，无捕获的用户态断点或内核 panic；
securityd、mobileactivationd 已按需启动，但实际画面仍在迁移进度条。
新加载的 44 个原版插件被签名检查拒绝；u38 已核验其 2,589 个代码页。
u37 同时纠正按需配置遗漏的六项上游核心服务自启动例外。
整盘 2,112 个已签名 Mach-O / 189,564 个代码页已一次性核验通过。
u39 的十分钟回放已消除签名拒绝，迁移插件出现正常退出，但实际仍为迁移进度条。
实际 Data 检查点仅剩约 3 MiB 空闲；u42 在保留已有文件、权限、扩展属性及卷 UUID 后扩容，
随后捕获到固定 3 GiB 窗口导致的启动内存不足。u43 的 4 GiB 模拟窗口对照已完成，
无内核 panic，Data 约有 307 MiB 空闲，实际仍显示迁移进度条；容量不足不是唯一阻塞。
u44/u45 另外采用固定版 ios-fuxi 的开发预配置方式，在独立 Data 副本中显式设置
`com.apple.migration/LastSystemVersion=20F66`。这是主动跳过首次迁移的开发配置，
**不是迁移实际完成的证据**；未预配置的 u43 检查点完整保留。
u45 中 datamigrator 两次正常退出，进度条消失，但仍是白苹果，只完成三帧复制。
没有签名拒绝或内核 panic；27 次用户态断点唯一匹配到 libxpc 的
`XPC API Misuse: %s`。下一步用固定版 UniXNU 上游线程快照工具直接读取具体报错及 UI 线程栈。
工具布局从本机编译对象 DWARF 推导，五个访问器与实际预链接内核逐字节核对。
以上均仅限电脑；不代表桌面、触摸或 A660 GPU 已在 UniXNU 完成。

以下为已经完成的前序步骤：
u20 已通过原版 MobileGestalt 的四字节 `chosen/display-scale` 输入修正 FBS 显示模式断言。
u24 已实测修复 AppleKeyStore 的注册与客户端类名：6 次连接，selector 0/7/17/35
实际返回成功，未观察到此前的客户端 MACF 拒绝、用户态断点或内核 panic。
这里的状态服务只描述易失 RAM 环境，不实现密钥、密码、SEP 或加密存储。

u25 将独立核对的 iOS16.5 IOSurface getter 接入实际内核：后备描述符为对象偏移 56，
宽/高/步长/格式/分配大小为 144/148/152/164/172。原版属性写入和新编译器的
getLength/prepare/complete 调用均已交叉核对。u25 当时的 slot282 只检查真实请求并明确拒绝；
后续 u31 已接通受限的单层 BGRA 软件复制和原版完成通知。GPU 生产者同步和桌面仍未验收。
最终 338 个显示入口、65,319 个指针和 30 个原始驱动代码区通过独立检查。
u25 历史证据入口为 `../../outputs/MIX4-UniXNU-display-u25/progress.json`。

以下保留 u09–u17 的历史步骤和失败记录，最新结果以上段与统一证据为准。

完整 iOS16.5 / 20F66 APFS 系统盘已在 QEMU 中由原始 Apple APFS 驱动挂载。
显式选择 `/sbin/launchd.ios` 后，PID1 的 dyld 已实际进入 ARM64 EL0 并发出系统调用。
43 个共享缓存已在运行时完成 165,818 个原始签名块核验；launchd 已实际输出版本信息和“Early boot complete”。
已补齐缺失的 21 项服务配置，并通过 NativeRamBlock、原始 IOStorageFamily 和原始 APFS
将独立的 RAM Data 卷以可写方式挂载到 `/private/var`。u12servicesclean 实际记录到
67 次读、43 次写、0 次 I/O 错误；后续 u12writeentries 为 113 次读、848 次写、0 次错误，md0 系统卷仍为只读。
launchd 已报告成功启动 SpringBoard、backboardd、runningboardd、logd 等服务进程。
u13cryptex 已验证：恢复两个 trampoline 库的访问路径并精确补入 8 项开发信任后，
此前的缺库退出与签名拒绝消失。SpringBoard 随后在 FrontBoardServices 触发 SIGTRAP；
唯一指令匹配及第二处独立指令核对给出实际缓存偏移，原始 CFString 为
`failed to find the main CADisplay`，接下来需要发布实际主显示设备。
**尚未证明 SpringBoard 完成初始化或渲染桌面，不能上机作为桌面镜像。**

u14 已从实际 iOS16.5 原始驱动重建显示接口：Legacy 实例为 `0x1660` 字节、
338 个入口、9 个抽象方法，用户客户端有 87 个命令；不能复用上游 iPadOS17 的
`0x18a0` / 358 / 90 布局。原始继承链、构造/析构导入及全部命令表逐项核对。
新建 `drivers/OdinDisplay`，GOP 映射与尺寸回读代码已通过实际内核编译器
`-Wall -Wextra -Werror` 和独立 338 项调用表核对。
**本轮对象未链接或运行；主显示注册、IOSurface 送帧和完成通知仍未实现。**
没有重复运行没有新显示实现的旧 QEMU，也没有操作手机。

u15 已实际链接并在电脑回放中完成原版显示驱动 `start()`、1080×2400
帧缓冲映射和原版客户端进入。客户端读取 `dot-pitch` 时暴露原驱动对
AppleARMIODevice 的空指针依赖。u16 根据实际 selector28 / slot188 /
uint32 输出核对，改为返回原版缺少属性的错误，运行已越过这次崩溃，
随后准确停在抽象 slot212。u17 将此查询的实际 scalar/64 字节结构输出
合同接入明确的“不支持”返回。u17 已完成 300 秒电脑回放，无内核 panic；
但保存的帧缓冲经实际渲染检查仍是日志控制台。独立匹配本轮缓存 ASLR 后，
确认有 7 次用户态断点，原始断言为 `FBSDisplayMode cannot be configured as requested : %@`。
旧的主 CADisplay 缺失断言未再次观察到；这不等于 SpringBoard 已完成初始化。
三版均已独立核对最终内核的全部 338 个显示入口，并保留原始 30 个驱动 text。
**原版显示启动成功不等于桌面已绘制；当前还未接通实际画面送帧。**


遵守用户“你不让我进桌面就不要动我手机”的要求：本轮没有 ADB、fastboot、
设备查询、重启或刷写，也没有生成新的手机 boot.img。QEMU 的硬件树、VMM 标记
和大内存窗口仅用于电脑回放，不是 SM8350 驱动或真实手机内存分配结果。

## 已修复并留存证据

- BCM2837 构建被 SDK 兼容头误标成 Apple 平台，导致大内存时 4K/16K 页合同冲突；已修复并验证完整 2,476,732,416 字节根盘挂载。
- 旧静态 `/sbin/launchd` 没有 dyld vnode，不能直接复用它的启动链。新增仅 DEVELOPMENT 的显式 `odin-init-path=/sbin/launchd.ios`，保留正常 exec/AMFI 检查。
- 原始 AppleFSCompression 对资源映射表进行 50 字节固定比较。修正副本中 8,340 个合成压缩文件的 16 字节冗余表头，其他镜像字节逐字节一致；关键文件代码页哈希再次通过。
- 支持 PAN 的 Cortex-A76/SM8350 需要相应 copyin/out 处理；已启用 PAN 并将编译目标调整为 ARMv8.1。保留失败编译、宏检查、成功构建和回放证据。
- 43 个共享缓存文件的原始签名代码页全部通过独立审计。开发信任表只包含已审计文件的 cdhash（具体输入见统一证据）；这是本机所有者开发信任，不是 Apple attestation。30 个原始 kext text 保持字节一致，65,319 个指针独立校验通过。
- 显式开发启动可发布既有 `dyld_flags`、指定实际 Cryptex 缓存目录；启用上游先核验原始 16K 签名、再派生 4K 页哈希的兼容路径，未关闭 AMFI。
- 对实际 iOS16.5 IOBlockStorageDevice 接口进行静态核对：类大小 0x90、190 个虚函数槽、176 项继承绑定。独立审计与实际回放使用同一内核；保留 30 个原始 kext text。
- 原始 APFS 不接受直接发布的 md2 作为 Data 后端；改用真实 IOKit 块设备提供者，原始 IOStorageFamily 发布 disk1s1 后成功挂载。Data 明确为易失 RAM，不包含 UFS 持久化实现。
- 去掉诊断时额外加入的 `StandardErrorPath=/dev/console` 后，logd、distnoted、backboardd 均成功启动，未再出现原 EACCES。原始二进制和签名未改写。
- 精简跟踪使用实际 `_write` / `_write_nocancel` 入口硬件断点；`_write_internal` 在这些入口内被编译器内联，不能用它作为完整控制台采集依据。保留反汇编和首轮采集的局限。
- u13 新盘核验 45,064 项既有文件载荷及其权限、属主未改变；只新增 `/usr/lib/libobjc-trampolines.dylib` 和 `/usr/lib/libffi-trampolines.dylib` 指向原有 Cryptex 文件的链接。8 项新增依赖的 197 个代码页均通过已有签名哈希核验。
- u13 实际 RAM Data：109 次读、935 次写、0 次 I/O 错误；无内核 panic。原始用户态断言和 SIGTRAP 仍存在，不能将无 panic 等同于桌面可用。

## 当前产物与复现入口

- 统一证据：`../../outputs/MIX4-UniXNU-host-u12/progress.json`（路径以工作区为准）。
- 内核：`build/ios16-prelink-u12match/kernel.prelinked.experimental.macho`，SHA256 `0921dad787ce8e41272bdef6e04ed6cb38eb9bc943c677ff4cadf0fe46278591`。
- 系统盘：`build/root-media/system-cryptex-links-u13.apfs`；此前对照盘 `system-launch-services-u12.apfs` 保留。
- 独立易失 Data 种子：`build/root-media/host-data-u11b.apfs`；服务开发信任：`build/root-media/services-cryptex-trust-u13.bundle`，74 个精确条目。
- 用户态显示断言证据：`../../outputs/MIX4-UniXNU-host-u12/u13-display-assertion.json`；重放入口：`scripts/run_u12_host_services.ps1`，显式指定 u13 系统盘、信任表与 `build/desktop-handoff-u13cryptex/kernel.macho.adt`。
- 块设备源码及构建证据：`../../outputs/MIX4-UniXNU-host-u12/odin-host-u12-final-source.tar.gz`。归档内后续警告检查调整不代表已重新链接回放所选内核。
- u14 显示接口和 GOP 映射编译证据：`../../outputs/MIX4-UniXNU-display-u14/progress.json`；静态核对与生成、编译入口见 `scripts/audit_odin_display_abi.py`、`scripts/audit_odin_display_protocol.py`、`scripts/prepare_odin_display_interface.py`、`scripts/compile_odin_display_annotation.py`、`scripts/check_odin_display_interface.py`。
- u15/u16 显示接入、原版客户端崩溃与修补运行证据：`../../outputs/MIX4-UniXNU-display-u16/progress.json`；独立构建在 `build/display-owner-u15`、`build/display-owner-u16`，u17 可选查询候选在 `build/display-owner-u17`。回放入口 `scripts/run_u15_host_display.ps1 -BuildTag u17 -OutputTag 新名称 -Seconds 300`，仅电脑使用。
- u17 显示配置断言及控制台截图：`../../outputs/MIX4-UniXNU-display-u17/progress.json`。`scripts/analyze_u17_display_runtime.py` 用唯一原始指令匹配和另一处独立指令锚点核对本轮 ASLR，不能套用 u13 的缓存偏移。
- 状态：`migration-status.json`；实时阻塞、实际启动参数和系统调用见统一证据引用的 replay/syscalls。
- 构建：`scripts/build_offline_kernel.sh`、`scripts/link_offline_kernel.sh`；XNU 修补清单：`patches/xnu/series`。
- 系统盘修复：`scripts/repair_mkapfs_spaceman.py`、`scripts/repair_mkapfs_resource_maps.py`；后续打包工具修补：`patches/root-media/`。
- 可执行文件审计及信任：`scripts/inspect_root_exec.py`、`scripts/build_development_trust.py`。
- 电脑回放：`scripts/qemu_early_entry.py`；`--syscall-log` 只读取实际保存的 ARM64 syscall 状态，不改内核指令。

## 尚未完成

受限单层 BGRA 的 CPU 复制及原版完成通知已经运行验证；尚需定位 libxpc API misuse 和 UI 初始化阻塞并实际验证桌面，扩展生产者同步及显示格式；真机 PMGR/platform 和大根盘连续内存交接；
UniXNU 原生显示、ST HID 与 A660 Metal。旧 HakiOS 的桌面、触摸和 GPU 实测不能算作 UniXNU 验收。
历史 core-u03 构建细节保存在 `README-core-u03-historical.md`。
本目录未发布到远端，既有源代码及复用组件保留原始许可。
