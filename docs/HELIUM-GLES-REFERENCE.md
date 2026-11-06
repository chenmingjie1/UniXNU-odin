# Helium GLES reference and the odin integration boundary

Reviewed source: [HeliumStudio-Dev/hackios-xnu-kernel](https://github.com/HeliumStudio-Dev/hackios-xnu-kernel/tree/57722468a3774e2ec60017705ec356ae9b31f40e),
branch `raphael-bringup`, commit `57722468a3774e2ec60017705ec356ae9b31f40e`.
Target: SM8150 / Adreno 640, iOS 16.5 / 20F66.

The device README explicitly calls the latest baseline GLES-only and says that
historical Metal results do not qualify it. The historical RAPHAEL log does
document real GPU renderer identification, triangle readback and CoreAnimation
submissions, plus improved physical operation. Those are useful engineering
results. Its remaining 32–34 ms long frames are not a stable 60 FPS result, and
none of its device results is evidence that odin already uses this path.

## Concrete route to reuse

1. `userland/src/inject.c::opengl_es()` loads `libhakios.gl.dylib` in backboardd.
   This happens before `window_server_fixes()`. Merely publishing `HakiosGPU`
   without the library cannot redirect the original compositor.
2. `userland/src/eagl.c::install()` replaces eight EAGLContext methods, including
   the inherited sharegroup/dealloc methods. The generated macro-context table
   comes from `eagl_slots.txt`, `mkeagl.py`, Mesa's GL XML and exported GL symbols.
3. `gl_osmesa.c` creates an OpenGL ES OSMesa context. The patched Mesa 25.0.7
   library chooses freedreno when a real GPU service opens; it can also fall
   back to software. A successful OSMesa context is therefore not a GPU pass.
4. `tools/mesa/hakios-drm` translates Mesa's MSM DRM requests to IOKit calls.
   Actual submissions and fences go through the kernel GPU service.
5. IOSurface-backed textures use `hakios_drm_surface()` for metadata and
   `drmPrimeFDToHandle()` for retained backing. Mesa's patched resource import
   expects linear BGRA, dimensions, stride, size and offset.
6. EAGL frame completion, surface synchronization and the display's presentation
   must agree. Its raphael TE-latched page flips and MiniIOSurface synchronization
   cannot be substituted for odin's original IOSurface contract.

## What cannot be copied unchanged

- A640 clocks, SMMU streams, GMEM, UBWC configuration, ZAP/GMU firmware and
  panel registers belong to SM8150. Keep the odin A660 backend and firmware.
- Kernel selector `0x7e` in that project describes/imports MiniIOSurface memory.
  Odin intentionally rejects it for the original IOSurface implementation.
  The reference DRM shim therefore cannot import our textures unchanged.
- `OdinSurfaceImport.c` supplies a public-original-IOSurface to userptr (`0x7d`)
  route. Its callback uses raw IOReturn values; the DRM shim maps them to errno.
  A wrapper must preserve that distinction and handle cached handle lifetime,
  read-only source backing, fences and safe cleanup. The current adapter only
  accepts writable, whole-page BGRA surfaces, not all compositor backing stores.
- Exact 20F66 method encodings, generated function-table slots and imports need
  qualification even though both systems use the same OS release.

## Build dependencies found locally

The Linux guest has clang-18, ld64.lld-18, LLVM binary tools, meson, ninja, bison
and flex. A broader search subsequently found the existing iPhoneOS16.5 SDK and
`xnu-clang++` wrapper under the older `xnu-work` build tree, outside the UniXNU
build directory. There is no installed Mesa build or `libOSMesa.8.dylib` in the
checked trees. The existing minimal linker stubs suffice for small verified
helpers; they are not a complete SDK for compiling Mesa. The pinned reference's
`mk-mesa.sh` explains the cross file, patches and library install names. Windows
Git transfer failed with connection resets; a redundant SDK archive download
was stopped after discovering the existing SDK. A subsequent Mesa source
archive download timed out after a partial transfer; it has not passed the
expected SHA-256 verification and is not used as build input. No Mesa or EAGL
frontend binary has been compiled or installed in this experiment.

Fetch and verify this source reference without operating the phone:

```sh
python scripts/fetch_helium_gles_reference.py --local-upstream ../hakios-upstream
```

The research directory stays local and is excluded from the source publication.
The fetch script verifies every file against its pinned Git blob hash. Neither
it nor this review installs a GL frontend or establishes desktop acceleration.

## Physical acceptance

Original IOSurface import, real GPU command completion and pixel readback
passed on physical u91 after the authorized service access change. The u90
control was refused at IOServiceOpen. Next qualify freedreno renderer identity and a shader draw;
CP_MEM_WRITE does not exercise shaders or rasterization. Finally qualify actual
backboardd EAGL calls, sustained GPU frame submissions, fence-backed presentation
and the same physical scroll gesture. Preserve CPU rendering until that complete
path can be tested without sacrificing the working desktop.
