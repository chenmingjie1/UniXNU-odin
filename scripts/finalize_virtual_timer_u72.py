"""Record the actual u71 failure and the separately verified u72 source fix."""
from pathlib import Path
import datetime, hashlib, json, subprocess, sys

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
BUILD = DEV/'build/virtual-timer-u72'
OUT = ROOT/'outputs/MIX4-UniXNU-desktop-u72'
PREVIOUS = ROOT/'outputs/MIX4-UniXNU-desktop-u71'
SNAPSHOT = PREVIOUS/'resident-snapshots/20261106-022309'
LLVM = ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

kernel = BUILD/'kernel.prelinked.experimental.macho'
disassembly = subprocess.run([str(LLVM/'llvm-objdump.exe'), '-d',
    '--disassemble-symbols=_fiq_context_init', str(BUILD/'native-real-iig.macho')],
    capture_output=True, text=True, check=True).stdout
assert '<_fiq_context_init>:' in disassembly
assert 'CNTV_CTL_EL0' in disassembly and 'CNTP_CTL_EL0' not in disassembly
sys.path.insert(0, str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np
native_bytes = (BUILD/'native-real-iig.macho').read_bytes()
final_bytes = kernel.read_bytes()
native_image, final_image = np.macho(native_bytes), np.macho(final_bytes)
address = next(va for va, names in np.exports(native_bytes, native_image).items()
               if '_fiq_context_init' in names)
native_offset = np.backed_offset(native_image['segments'], address, 0x38, len(native_bytes))
final_offset = np.backed_offset(final_image['segments'], address, 0x38, len(final_bytes))
assert native_bytes[native_offset:native_offset+0x38] == final_bytes[final_offset:final_offset+0x38]
(BUILD/'fiq-context-disassembly.txt').write_text(disassembly)
proof = json.loads((DEV/'build/qemu-early-entry-u72core7verified/verification.json').read_text())
assert proof['kernel_sha256'] == sha(kernel)
assert proof['hardware_breakpoint_reached'] and proof['hardware_breakpoint_symbol'] == '_machine_startup'
verification = dict(source_build=True, at=now, kernel_sha256=sha(kernel),
    fiq_virtual_timer_write_preserved=True, fiq_physical_timer_write_removed=True,
    final_prelinked_function_matches_source_build=True,
    source_reference='work/hakios-upstream/xnu/hakios.patch: _enable_virtual_timer',
    independent_soc_reference='work/UniXNU-components/Reference-haydn-iamojz-9710ddf99b1d23b54b93cd683f6af1e37a43c87b/patches/xnu/0001-sm8350-el1pcen-physical-timer.patch',
    qemu_breakpoint='_machine_startup', qemu_passed=True,
    physical_fix_verified=False, physical_desktop_verified=False)
(BUILD/'verification.json').write_text(json.dumps(verification, indent=2)+'\n')

actual_path = PREVIOUS/'device-outcome.json'
actual = json.loads(actual_path.read_text())
actual.update(framebuffer_snapshot=str(SNAPSHOT/'framebuffer.png'),
    read_only_snapshot=str(SNAPSHOT/'status.json'),
    framebuffer_observation='UniXNU menu with native post-VM checkpoint 0x4c; no desktop',
    pre_vm_checkpoint='0x35', post_vm_checkpoint='0x4c',
    panic_format='Undefined kernel instruction: pc=%p instr=%x @%s:%d',
    exact_fault_pc_available=False,
    next_fix_basis='Current path writes CNTP_CTL_EL0 in fiq_context_init; HakiOS and SM8350 haydn avoid this access',
    physical_desktop_confirmed=False)
actual_path.write_text(json.dumps(actual, indent=2)+'\n')
prior_manifest_path = PREVIOUS/'manifest.json'
prior_manifest = json.loads(prior_manifest_path.read_text())
prior_manifest.update(device_tested=True, physical_resident_usb_verified=True,
    physical_desktop_confirmed=False, latest_device_outcome=str(actual_path))
prior_manifest_path.write_text(json.dumps(prior_manifest, indent=2)+'\n')

manifest_path = OUT/'manifest.json'
manifest = json.loads(manifest_path.read_text())
manifest.update(parent_release='u71', kernel_change='Source-built HakiOS guard avoids EL1 physical timer access on non-Apple platforms',
    source_fix_verification=str(BUILD/'verification.json'), device_tested=False,
    physical_desktop_confirmed=False)
manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
(OUT/'README.md').write_text('''# MIX 4 UniXNU u72

u71 loaded the complete System/Data and reached post-VM stage 0x4c on the
physical phone. Read-only USB captured an undefined-instruction panic and a
menu framebuffer. The exact fault PC is not exported by u71, so the failing
instruction itself has not been read back.

The reached source path next calls fiq_context_init. Its u71 compiled code
writes CNTP_CTL_EL0. HakiOS xnu/hakios.patch guards this physical-timer write
on non-Apple platforms; the independent SM8350 haydn port documents the same
hypervisor restriction. u72 ports that guard into source and rebuilds XNU.
Disassembly of the final prelinked kernel preserves CNTV_CTL_EL0 and removes
CNTP_CTL_EL0 from fiq_context_init. This is a concrete compatibility fix,
pending physical verification.

The complete system, Data seed, ADT, trust cache, resident handoff, loader,
MMCX hold provider and 141 baseline firmware modules are retained. The u72
boot image is byte-identical to u71 because only the USB-served kernel
changed; the new kernel hash and pinned media manifest identify the fix.
Use the paired u72 media server, not an isolated boot image.

Computer checks: full original-kext prelink audit, compiled function
disassembly, production USB/readback callbacks, firmware extraction, and
QEMU core7 execution through fiq_context_init to machine_startup. QEMU uses
an explicit generic GIC/timer overlay and does not validate SM8350 hardware.

u72 has not booted on the phone. The phone remains in the u71 panic; no
remote reset has been sent. Recovery to Android is needed for the next
authorized RAM boot. No partition writes. UniXNU desktop, native touch and
A660 Metal remain unverified/unlinked as recorded in the manifest.
''')
(OUT/'HakiOS-doc-review.md').write_text('''# HakiOS guide cross-check, 2026-11-06

Read the rendered page at https://hackios-web.vercel.app/zh/guide/how-it-works
using the in-app browser. It says the Chinese translation is not available
and displays the English original.

Relevant points: fastboot RAM boot -> firmware -> xnuloader -> patched XNU
with compiled drivers -> launchd -> supplied Darwin userspace. Driver build
selection CONFIG_HAKIOS_<NAME> and runtime boot arguments are separate; a
boot argument alone cannot provide an unlinked driver. The command line
limit is 607 characters. QEMU uses generic ARM/GIC and virtio; its success
does not establish physical device-driver success.

This overview is not an SM8350 register recipe. The specific timer guard
was read in HakiOS source and cross-checked with the haydn SM8350 patch.
The current UniXNU port reuses HakiOS-derived resident handoff and the
working firmware/display hold. It still uses a separate native kernel;
the HakiOS touch and A660 Metal implementation is not linked into it yet.
''')
status_path = DEV/'migration-status.json'
status = json.loads(status_path.read_text())
status.update(updated_at=now, phase='u72 HakiOS timer compatibility fix built; physical test pending',
    prepared_candidate=str(OUT/manifest['artifact']), prepared_candidate_device_tested=False,
    release_manifest=str(manifest_path), latest_device_outcome=str(actual_path),
    current_device_state='u71 panic retained; no device reboot or further launch requested',
    latest_physical_result='u71 passed VM initialization, reached 0x4c, then undefined-instruction panic; framebuffer remains menu',
    latest_computer_work=str(OUT/'README.md'),
    physical_desktop_verified=False, full_ios_desktop_confirmed=False,
    timer_fix_candidate='u72 source-built HakiOS non-Apple physical timer guard',
    timer_fix_computer_verification=str(BUILD/'verification.json'),
    timer_fix_physical_verified=False)
status_path.write_text(json.dumps(status, indent=2)+'\n')
print(json.dumps(verification, indent=2))
