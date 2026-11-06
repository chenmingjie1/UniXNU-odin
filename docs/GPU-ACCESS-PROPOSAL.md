# GPU service access experiment — explicitly authorized for RAM boot

The u90 physical probe created an original IOSurface successfully, then
`IOServiceOpen(HakiosGPU)` returned `0xe00002e2`, which the matching XNU
`IOReturn.h` defines as `kIOReturnNotPermitted`. No surface import, submission,
fence or GPU pixel readback followed that failure. The phone continued to run
the original UI; the captured final framebuffer shows Settings.

The source kernel already contains `zzw-native-adreno-sandbox-grant.patch`.
Its `native_sandbox_grant(service)` only applies when a service declares a
`NativeSandboxGrantProcess` property. The current HakiosGPU service sets no
such property. The hook replaces the matching IOKit MACF open-service,
open-client and filter decisions for the named processes. It also participates
in a separate set-properties check. It is a security exception, not a
performance flag, and process-name matching is not a code-signing identity.

Candidate addition in `HakiosGPU::start`, immediately before `setName`:

```cpp
setProperty("NativeSandboxGrantProcess", "SpringBoard,backboardd");
```

Scope: the port's HakiosGPU service, those two process names, and a new
temporary RAM-boot candidate only. No phone partition write, global sandbox
disable or change to the original Apple kext code is proposed. This should
address the observed access gate; it does not establish that surface wiring,
GPU commands or desktop acceleration will subsequently work.

Automatic approval review initially rejected applying this property because
the existing GPU request did not specifically authorize weakening the sandbox
boundary. The user subsequently explicitly authorized this exact service and
process-scoped exception for the next temporary RAM boot. The u91 source now
contains the property; its build retains the u90 signed probe, system media,
original Apple driver code and UI exit observations. Build and physical results
are recorded separately in STATUS.md. This is a development experiment, not
an endorsement of process-name-based access control for a production system.
