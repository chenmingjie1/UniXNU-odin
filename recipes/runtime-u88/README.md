# u88 运行包对应的保留源码

本目录保存此次运行包对应的 DarwinBoot、BDS、USB 文件表 / 读回符号、UI 辅助库和固件 inventory。不是整个固件工具链的独立重建工程。

完整入口：[桌面运行包](../../docs/DESKTOP-U88-RUNTIME.md)。所有源码保留原有声明；DarwinBoot 固定上游 revision 与所用 Mu archive 哈希见各 `verification.json`。`OdinTouchRpmhFingerprint.h` 是已授权公开的保留固件字节指纹，用来匹配原实测 RPMh provider；它不是通用机型数据。
