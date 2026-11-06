# Device status: 2026-11-06

Target: Xiaomi MIX 4 / odin, SM8350, iOS 16.5 / 20F66. Latest physical feedback: u88.

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
