# Device status: 2026-11-07

Target: Xiaomi MIX 4 / odin, SM8350, iOS 16.5 / 20F66. Latest physical feedback: u89.

- u87: continuous real operation possible; lag remained.
- u88: continuous operation still possible; lag remained; bottom upward swipe did not return to Home.
- The original SpringBoard global idle-disable assertion remained active in the qualified capture (~384 seconds): screen on, digitizer enabled, unlocked. This is a development workaround, not normal power management.
- The later resident snapshot contained 393 accepted physical HID reports, 9 downs and 9 ups, with no active contact left and no recorded malformed/bus/report failures. Accepted HID reports do not prove correct system gestures.
- A separate 120-second observer started after the user's action recorded no new touch reports. Its idle timings cannot measure the user's swipe latency.
- CPU dirty-span copying reduces scanout work, but cannot be described as GPU composition. Earlier full copies took approximately 31-32 ms; a later sampled dirty copy took about 21 ms. These are copy timings, not end-to-end latency or an FPS measurement.
- A660 initialization, firmware handoff and offscreen tests are separate from desktop rendering. The desktop GPU composition path remains unimplemented/unverified; IOSurface import is disabled.

## Known artifact identities

u85-u88 source kernel SHA-256:
`3f95a57bbd346cf8a8c493d365cd98299ce17d21255fa3f5400c133f72bd9d1b`

u85-u88 RAM boot image SHA-256:
`a77af91958c3fe2ede4f6da1e6fae9f9424f99b8dce2ffc39e0e9ea854a4676e`

u88 changed the signed UI helper and RAM System/trust media, not this kernel or boot image. None of those binary artifacts is distributed here.

## Bottom-gesture investigation

The pinned OddlyLabs/unixnu-fuxi reference documents real touches being rejected by SpringBoard's Home edge recognizers when the digitizer event lacks `kIOHIDDigitizerEventFromEdgeTip` (0x800). Its source marks contacts beginning at an edge for their entire lifetime. The odin descriptor already reports both Tip Switch and confidence, including confidence on lift.

This is a concrete compatibility lead, not yet a confirmed cause on odin. The reference has different original HID family versions and hard-coded virtual method slots. Those offsets must be derived from the exact 20F66 family before any native hook can be enabled. No foreign-family vtable has been installed on the phone.

## u89 prepared candidate

The native edge-contact wrapper has been implemented for the exact 20F66 family, with a 219-slot driver table, dispatch slot 198, 37-slot event table and measured event accessors/children offset. It is restricted to the exact original table and this board's own digitizer. `odin-touch-edge=1` enables it; without the argument it leaves dispatch unchanged.

Contact lifetime tests, 70,020 existing report-bridge assertions, native compile/link, original-driver integrity audit and generic core7 bootstrap replay passed. The isolated RAM boot image is prepared. This is not yet a physical Home-gesture pass and does not claim a latency fix.

Kernel SHA-256: `3e148e97163396e01c31d7a23bcc4d338f230d1439340df8023a551b364fca56`

Boot image SHA-256: `c77f8289746db7f6407adb263c4f56d03aebcb417d4752363904a94d27d0c00a`

### First u89 physical result and startup ordering correction

The user reported that the initial u89 boot was unresponsive. The saved resident state contained 294 accepted/forwarded HID reports, 11 edge-marked finger events, no skipped event ABI checks and no kernel panic. The UI policy reported screen off, digitizer disabled and locked, despite a subsequently acquired idle-disable token. This is not a Home-gesture pass.

The host requested the idle assertion after the UI had already auto-locked. That API prevents future idle lock and does not unlock an already locked UI. The media server now provides `--arm-ui-idle-assertion` for the qualified u88/u89 fixture: after resident handoff, it waits for post-VM entry, then requests the fixed original-API command before the helper's first poll. A second temporary u89 run is being validated with this ordering. No new image, input injection, partition write or arbitrary-address command is required.

The exact 20F66 UIKitCore implementation also reads digitizer field `0xb0007` and maps mask bit `0x800` to edge type 1 (implementation starts at unslid cache address `0x18918a784`). This independently supports the metadata contract; physical Home navigation still requires user confirmation.

### Second u89 physical result: restart, not Home navigation

The user confirmed taps worked after the earlier idle-assertion request. An
upward swipe was followed by a black screen, white spinner, and the desktop;
scrolling remained extremely slow. The 180-second observer recorded backboardd
PID 11 last seen at 0.059 seconds and PID 107 first seen at 12.731 seconds.
SpringBoard PID 5 was last seen at 9.576 seconds and PID 111 first seen at
15.889 seconds. Preferences also changed from PID 97 to 124 later. This records
process replacement, not its cause. The order of these sampled boundaries does
not prove that the edge wrapper caused the restart or that SpringBoard was the
first failing process. No exit signal/namespace/code or full crash stack was
captured, and resident kernel panic state was clear.

The analyzer now groups thread samples by PID and reports process lifetimes and
replacement intervals instead of conflating two instances of the same program.
There were 801 CPU copies during that observation, averaging 23,908.8 us of
copy work; this is not a GPU metric, scrolling FPS or input latency.

A public-original-IOSurface-to-userptr adapter is now compiled and tested on
the computer. Its import/lifetime mock tests pass with ASan/UBSan, and its iOS
16.5 arm64 library has passed signature audit. It has **not** been deployed,
physically qualified or integrated into desktop Metal at the u89 checkpoint. See
[the remaining GPU integration boundary](GPU-INTEGRATION.md).

## u90 original-surface probe, physical result

The paired phone accepted a temporary u90 RAM boot. The read-only USB server
delivered 3,040,419,734 bytes in 2,904 requests and retained resident control.
No partition was written. The original UI idle assertion was armed before
helper startup. A later scanout capture shows Settings, with continuing CPU
presentation and no recorded kernel panic.

The helper created a 64x64, 16KB original IOSurface, wrote the CPU canary and
reported phase 2 success. Opening HakiosGPU failed at phase 3 with
`0xe00002e2` / `kIOReturnNotPermitted`. Consequently no original-surface GPU
import, command submission, fence or readback was qualified. Backend offscreen
success remains separate from this failed client access and desktop rendering.

The UI exit observer also recorded a backboardd exit with status `a`, namespace
2, code `a`, and a SpringBoard exit with status `9`, namespace 15, code `0`.
Resident text packets truncate some boundary characters, including PID digits;
do not infer exact PIDs or causal ordering from those lines. The reason records
are more specific than prior PID replacement observations but are not a crash
stack or proof of what caused the exits.

u90 source kernel SHA-256:
`40323e8e87955d5ea76f8389dc862b0c191fdfc2cd1df68ee1eb6c26b19c7db9`

u90 boot image SHA-256:
`59bf91dada6e3c25e4b126e5558ca5ccc556553028a80b68f5743efe54bae88d`

## u91 GPU client access experiment

Automatic review initially rejected adding a native service grant because it
weakens a sandbox boundary. After seeing the precise scope and risk, the user
explicitly authorized the exception in the next RAM-boot image. Only HakiosGPU
declares `NativeSandboxGrantProcess=SpringBoard,backboardd`; this is a development
security exception and process names are not signing identities.

The native GPU service has been rebuilt and linked with the u90 observation
code and unchanged u89 touch/display archives. The original-driver audit passed
65,319 pointers, 30 unchanged original-kext code ranges and 17 real IIG
implementations. The exact kernel also passed the generic core7 bootstrap
breakpoint at `_machine_startup`; this does not emulate an Adreno or prove any
phone GPU operation. Packaging retained 141 exact baseline firmware files and
passed the read-only USB protocol checks. The signed probe/System/trust media
are reused unchanged from u90.

Physical u91 result: the service opened, original IOSurface userptr import
succeeded (handle 1, 16,384 bytes, 64x64), command submission returned fence 1,
the fence wait succeeded and the 4,096-word CPU readback had zero mismatches.
Phase 8 reported result 0 / mismatch 0, followed by phase 10 result 0 /
passed 1 after cleanup. The four CP_MEM_WRITE operations changed words 0,
2048, 4032 and 4095; all other words retained the canary. This is a real GPU
memory/command/fence/readback result, not a shader/rasterization test or
accelerated desktop composition. A subsequent captured scanout shows the
SpringBoard icon-editing desktop. The existing UI is left running, and the
resident panic record remains clear.

u91 source kernel SHA-256:
`2851c491cf6d7115ef1c7b3dec7187da1b812e8d79c23c4330bd39c0ab9a4564`

Local evidence: u91 resident snapshot `20261107-010346` and
`build/gpu-surface-import/u91-probe-observation.txt`. A source-only summary is
stored in [GPU-PROBE-U91.json](GPU-PROBE-U91.json). No raw screen image is
published.

The boot image hash remains identical to u90 because the changed XNU payload
is delivered through the pinned read-only media server, not embedded in the
small UEFI boot image. The source kernel hash and media manifest distinguish
these experiments.
