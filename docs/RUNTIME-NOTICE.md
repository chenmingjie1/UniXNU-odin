# u88 运行包来源与声明

这套运行包冻结本项目 u88 保留实测输入，包含基于 XNU / UniXNU 的预链接内核、原版 iOS 16.5 用户态 System、离线 QEMU 测试 Data，以及 MIX 4 固件衔接代码和既有固件组件。源码和各上游的原有版权、许可证继续适用；本项目没有把这些内容统一改为 MIT。

项目源码：https://github.com/chenmingjie1/UniXNU-odin

源码版本与组件 revision 见仓库 `source-pins.json`，构建配方见 `recipes/u85-u88`，本次辅助库 / 固件生成源码快照见 `recipes/runtime-u88`。这套二进制与这些保留记录对应；仓库尚未提供从全新环境重建所有相同二进制的完整闭环。SDK / IIG 来源另见 `docs/BUILD-INPUTS.md`，Apple System 原始输入来源见 `docs/SYSTEM-HOST-INPUT-U80.md`。

本包没有个人手机 Data 备份、已登录账号、账号凭据或私钥。Data 保留离线测试生成的系统数据库、UUID 与日志。各组件许可证文本随核心包保留在 `licenses/`。
