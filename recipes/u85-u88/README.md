# u85～u88 保留构建资料

中文说明入口：[`docs/BUILD-U85-U88.md`](../../docs/BUILD-U85-U88.md)。

本目录从原 Linux 构建虚拟机与已保留的设备打包目录提取开发配方。本次采集日期为 2026-11-07；原物理测试与 u85～u88 记录为 2026-11-06。没有为便于阅读而把历史绝对路径改成看似可直接运行的新构建系统。

| 路径 | 内容与使用方式 |
| --- | --- |
| `guest/build_offline_kernel.sh` | 虚拟机实际 Make 入口，放置在 `/home/odin/unixnu-odin-build/` |
| `guest/record-clang`、`guest/record-clang++` | 通过 `CC` / `CXX` 注入的编译记录包装器 |
| `guest/evidence/odin-gpu-u85` | u85 归档、owner 接入与链接配方 |
| `guest/evidence/odin-touch-u75/link_kernel.sh` | u85 最终链接配方使用的前置链接脚本 |
| `guest/build_crypto_archive_import.py`、`guest/build_pthread_archive_import.py` | 根据归档 receipt 和文件哈希核对原始源码的构建适配器 |
| `guest/crypto-import.json`、`guest/pthread-import.json` | 对应源码的逐文件哈希；receipt 的个人电脑路径已移除 |
| `guest/native_prelink.py` | 构建脚本实际导入的 Mach-O 解析辅助工具 |
| `guest/bin/xcrun` | 解析原构建环境已知工具路径的适配器 |
| `guest/iig-tools/iig-8796-cached` | 校验 IIG 输入和生成缓存的适配器；不包含生成缓存本体 |
| `upstream-tools` | 从虚拟机工作树保留的上游工具与组件目录快照，审阅时按 `upstream/scripts/` 和 `upstream/components.toml` 对应 |
| `compile-records` | Clang 命令记录与平台组件编译命令；保留原始 JSON / JSON fragment 格式 |
| `reference-nx769j` | 板级预链接脚本实际使用的固定版本参考 profile 与 literal-pool 校验工具 |
| `evidence` | u85 预链接产物信息、seal 日志、XNU 来源与 u88 帧缓冲几何回读 |
| `disclosure-manifest.json` | 本次新增公开文件的大小、SHA-256 与覆盖范围 |

除明确标注为 u85 专用目录保留物外，当前虚拟机编译记录反映的是本次采集时工作树的接口与路径，不能据此保证历史任意对象完全一致。复现前需要检查源树、SDK、补丁和生成输入。

## 来源与许可

- XNU 基线来源：`apple-oss-distributions/xnu`，revision `aca3beaa3dfbd42498b42c5e5ce20a938e6554e5`，版本 `8796.101.5`。
- `upstream-tools` 与虚拟机中的 UniXNU 工具基于仓库 `source-pins.json` 所列 UniXNU 源码，并含既有 Linux 构建适配。相关文件沿用上游许可，本目录不重新授权。
- `reference-nx769j` 来源：[`Asultop/UniXNU-NX769J`](https://github.com/Asultop/UniXNU-NX769J) 的保留归档标识以原项目 `source-pins.json` 中 `nx769j` 记录为准，revision `2a265afdbd95d45e4a90664157e793c3bfee3755`。此目录只保留实际使用的配置与工具，不把该机型的硬件结论转移到 odin。
- `native_prelink.py` 与原生预链接工具的来源参见项目固定的 XnuPrelink 组件与 [源码许可说明](../../SOURCE-NOTICE.md)。
- CoreCrypto / pthread import 文件包含公开源码的名称、版本与哈希，不包含系统镜像、厂商固件或登录凭据。

项目完整许可规则见 [SOURCE-NOTICE.md](../../SOURCE-NOTICE.md)。
