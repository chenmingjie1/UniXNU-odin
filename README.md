# UniXNU on Xiaomi MIX 4 (odin)

Experimental SM8350 / Adreno 660 port targeting **iOS 16.5 / 20F66**.

**2026-11-06, u88:** the physical MIX 4 displays the SpringBoard desktop and accepts real ST touchscreen input. The user can keep operating it, but scrolling is still slow and the bottom swipe does not return Home. This is a development source snapshot, not a finished daily-use system or a flashable release.

| Area | Observed result | Remaining work |
| --- | --- | --- |
| Boot / desktop | UniXNU source kernel reaches the physical desktop | Broader stability and complete build recipe |
| Display | Original iOS 16 framebuffer interface with CPU scanout copy | Performance; intermittent artifacts were reported in earlier versions |
| Touch | ST SALIXP 0x3640, real taps and scrolling | Lag and edge/Home gesture metadata |
| Idle policy | Original SpringBoard UI idle-disable assertion retained | Development workaround; normal lock/sleep integration remains |
| Adreno 660 | GPU initialization and offscreen self-test succeeded | Desktop GPU composition is **not implemented or verified** |
| Storage | System and Data media in RAM | No persistent iOS installation |

## Source map

- `drivers/OdinStTouch` and `package/OdinStTouch`: native HID device, bounded ST initialization, FIFO parser and report bridge.
- `drivers/OdinDisplay`: exact iOS 16 framebuffer interface and CPU scanout path.
- `drivers/OdinAdreno`: experimental A660 backend, runtime counters and thread sampling.
- `firmware`: board display/power handoff, resident USB control and bounded diagnostics.
- `host-input`: signed development UI helpers, including the original UI idle assertion.
- `patches`, `configs`, `dts`, `soc`: target kernel and board inputs.
- `scripts`: historical build, ABI audit, packaging and capture tools.
- `recipes`: preserved source recipes that previously lived under generated build directories.

Read [current evidence and limitations](docs/STATUS.md), [build inputs](docs/BUILD.md) and [source licenses](SOURCE-NOTICE.md).

## Build scope

The included native build scripts describe the existing Windows + Linux guest development environment. Many depend on earlier generated ABI contracts, pinned component checkouts, SDK inputs and private local media. **A fresh clone is not yet a one-command reproducible build.** Missing generated inputs must not be replaced with guessed offsets or another iOS version's ABI.

Host protocol checks can be run with Python and a native/cross-capable Clang:

```sh
python scripts/check_touch_bridge.py --cc /path/to/clang --clang /path/to/clang
```

This check validates the wire/report bridge; it does not prove physical gestures or GPU desktop rendering. Device testing so far uses temporary RAM boots. There is no supported permanent-flash procedure in this repository.

No Apple system media, original Apple driver binaries, vendor firmware blobs, signed boot images, SSH keys or account credentials are included. See `source-pins.json` for pinned upstream references. Historical notes are under `docs/history`; their old status statements do not describe u88.
