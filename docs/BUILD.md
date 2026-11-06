# 构建输入补充

SDK、完整 IIG 缓存与历史审计包已上传公开 Release，见 [中文下载与安装说明](BUILD-INPUTS.md)。`system-host-input-u80.apfs` 的 [原始输入获取、生成与配置](SYSTEM-HOST-INPUT-U80.md) 也已公开。以下是其余开发环境要求。

> 中文详解：[u85～u88 实际构建命令、profile、编译记录与启动参数](BUILD-U85-U88.md)。实际链接闭包与历史基础配方的区别也在该文逐项说明。

# Development build inputs

This snapshot preserves source and historical scripts; it is not yet a self-contained release builder.

## Required external inputs

1. The pinned UniXNU and component repositories from `source-pins.json`, resolved in the workspace layout used by the scripts.
2. Matching XNU source, patch series, target compiler, SDK headers and original iOS 16.5 / 20F66 ABI audit inputs. The scripts bind only measured original interfaces.
3. Separately obtained iOS System/Data media and original drivers. They are excluded from Git.
4. Device firmware inputs for the exact A660 board profile. Generated firmware byte arrays are excluded.
5. For the current native recipe: a prepared Linux build guest at `/home/odin/unixnu-odin-build`, including the earlier generated compile-command records and storage/display/HID ABI inputs listed in each script. SSH keys and known-hosts are local configuration, never repository content.
6. Windows packaging tools, EDK2 inputs and LLVM as referenced by the historical scripts. Paths must be configured for the local installation.

`board.toml` describes the initial core-only board selection; later display/touch/GPU development is linked by the versioned scripts. It must not be treated as a complete u88 build manifest.

## Preserved recipe entry points

- `scripts/rebuild_touch_u75.py`, `scripts/bind_touch_u75.py`: native original-family HID compile/bind path.
- `scripts/build_odin_gpu_u85.py`, `recipes/gpu-u85/*`: native A660 compile/link recipes; require separately generated private firmware source and prior guest artifacts.
- `scripts/prepare_ui_policy_root_u88.py`: isolated System copy with the signed UI policy helper. Requires private System media and signing inputs.
- `scripts/package_device_desktop_u64.py` and the release-specific readback/firmware builders: package a qualified kernel, System, Data and trust bundle.

A successful C/C++ compile, ABI audit or QEMU run is not evidence of usable physical touch, edge gestures or GPU desktop composition. Device evidence must identify its exact kernel/media hashes and the user's physical observations.

`firmware/OdinTouchRpmhFingerprint.h` is also excluded: despite its filename, it embeds retained firmware code bytes. The current local loader requires that separately generated, board-qualified input.

## Current RAM fixture startup ordering

For the u88/u89 native UI assertion fixture, use the media server's `--arm-ui-idle-assertion` option. It waits until kernel post-VM entry before writing the fixed policy command, then lets the signed SpringBoard helper acquire the original UI idle-disable token before auto-lock. Issuing `oem ui-wake` only after the screen has logically locked cannot be treated as a successful wake/unlock.
