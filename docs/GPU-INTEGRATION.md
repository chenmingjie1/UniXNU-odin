# Desktop GPU integration: current boundary

Target: MIX 4 / SM8350 / A660 / original iOS 16.5 (20F66).

The u89 physical run already enables `odin-gpu=1 odin-gpu-selftest=1`.
`OdinAdrenoOwner.cpp` initializes the backend and executes the opt-in offscreen
pixel test. The saved hardware log says the pixels were verified and explicitly
separates that result from native panel presentation. Repeating this test or
turning on the same argument cannot establish accelerated desktop composition.

The current display accepts a full-frame original IOSurface and copies it to
the scanout with the CPU. `OdinAdrenoService.cpp::surfaceBuffer()` still refuses
the HakiOS MiniIOSurface ID import because the original surface has another
object layout and lifetime contract. There is no installed/verified desktop
Metal frontend using this backend. A successful buffer import alone will not
change that fact.

## Original IOSurface adapter and physical probe

`host-input/OdinSurfaceImport.c` uses the original public IOSurface library in
the calling process, then imports those mapped pages through the existing
GPU user-memory selector `0x7d`. This avoids a global kernel ID lookup and avoids
copying MiniIOSurface offsets (including its extra shared-state page).

The adapter currently accepts only whole-page, non-planar BGRA allocations.
It validates dimensions, row length, allocation bounds, pointer arithmetic and
4K/16K page alignment. It acquires/releases a CPU lock while getting metadata,
releases that lock before wiring, and retains the surface until the GPU handle
is closed after all uses finish. A failed close retains the context for retry;
callers must also inspect it after a failed read-only-import cleanup. It rejects
the kernel's read-only fallback as a render target. It neither creates a fake
Metal device nor marks a submission complete without a fence.

Build:

```sh
python scripts/build_odin_surface_import.py
```

This uses the existing private build guest and exact local system cache. It
checks that all public imports exist in the 20F66 cache, runs ownership/bounds/
failure-path tests under AddressSanitizer and UndefinedBehaviorSanitizer, cross
compiles an arm64 iOS 16.5 dylib, and audits its ad-hoc signature. The artifact
is a library candidate, **not** a new boot image. That build performs no phone
operation or kernel change. Public-export presence does not prove a physical
import.

The separate u90 candidate compiles the same adapter and a bounded probe into
the existing signed SpringBoard UI helper. Physical execution created a public
64x64 BGRA original IOSurface and initialized its canary, then
`IOServiceOpen(HakiosGPU)` returned `0xe00002e2` (`kIOReturnNotPermitted`). No
GPU import, submission or pixel readback occurred in that run. The final
captured screen shows Settings; the desktop remains on the CPU path.

The user explicitly authorized a service-scoped native sandbox exception for
SpringBoard/backboardd in the subsequent u91 RAM-boot experiment. See
[the exception and its security scope](GPU-ACCESS-PROPOSAL.md). This fixes an
access policy change. In the subsequent physical u91 run, IOServiceOpen,
16KB original IOSurface userptr import, command submission, fence 1 completion,
all 4,096 readback words and cleanup passed. The probe uses CP_MEM_WRITE, not
shader drawing. This establishes the memory transport boundary, not a
renderer, compositor integration or desktop speed improvement.

The new [Helium GLES source review](HELIUM-GLES-REFERENCE.md) identifies a
concrete alternative frontend: EAGLContext -> OSMesa/Mesa -> freedreno ->
HakiosGPU. Its MiniIOSurface DRM shim needs adaptation for original IOSurface;
its A640 hardware parameters are not used on odin.

## Remaining integration and acceptance

1. Bind the adapter into a target-qualified Metal transport/frontend, with one
   retained import per live handle and bounded cleanup on queue errors. The
   adapter's callback takes raw IOKit return values, whereas HakiOS C++ Transport
   maps errors to errno; an integration must translate these explicitly.
2. Establish original IOSurface producer/consumer synchronization. Retaining
   memory does not replace GPU fences, cache maintenance or display retirement.
   Read-only backing stores need a separate import policy, not a writable alias.
3. Build the target shader compiler/runtime, register the actual Metal service,
   package the matching signed frontend/trust entries, and qualify original
   RenderBox/CoreAnimation calls. Do not install a stub device to claim success.
4. Verify a real client imports a surface, submits a draw, completes its fence,
   and presents those pixels. Correlate client identity and frame counters;
   backend initialization/self-test counters are not desktop submissions.
5. Compare the same physical scroll action and sustained operation before/after.
   A CPU copy time or an idle sample is not end-to-end latency or FPS.

The HakiOS reference is the pinned 2.3.4 source under the local research fixture;
its GPU service, `hakios-metal/src/iokit_transport.cpp` and Metal frontend are
separate parts. UniXNU's GPU porting guide likewise requires frontend, compiler,
IOSurface, fence and display integration. None of those guides establishes
compatibility with this port merely by matching the GPU family.
