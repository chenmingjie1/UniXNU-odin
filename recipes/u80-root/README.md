# u80 系统转换配方

中文入口：[system-host-input-u80.apfs 获取与生成](../../docs/SYSTEM-HOST-INPUT-U80.md)。

- `replay.py` 默认打印命令；`--run` 才执行，逐级校验历史输入与输出，拒绝覆盖。
- `replay-plan.json` 保存从基础 APFS 到 u80 的 11 级命令和 pin。
- `scripts/` 仅调整依赖路径的历史转换脚本。
- `upstream/` 保留 HakiOS APFS / 获取脚本及固定版本 core launch policy；周边完整下载、解压、用户态构建仍在固定版本的 HakiOS 树中执行。
- `helpers/` 为 u59 / u80 的历史源码、link stub、构建和签名审计记录；对应签名 Mach-O 与 development trust 元数据在 Release 小包中。
- `receipts/` 为历史生成记录，保留其当时的绝对路径、scope 与验证标记，不代表本次重新完成了相同实机验证。
