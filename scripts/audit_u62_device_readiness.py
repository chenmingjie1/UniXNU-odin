"""Check actual u62 desktop artifacts before any phone write; no device I/O."""
from pathlib import Path
import hashlib
import json

dev = Path(__file__).resolve().parents[1]
root = dev.parents[1]
build = dev / 'build/display-owner-u62'
run = dev / 'build/qemu-early-entry-u62nopasscode'
release = root / 'outputs/MIX4-UniXNU-display-u62'
verification = json.loads((run / 'verification.json').read_text())
command = json.loads((run / 'command.json').read_text())
progress = json.loads((release / 'progress.json').read_text())
kernel = build / 'kernel.prelinked.experimental.macho'
data = kernel.read_bytes()
digest = hashlib.sha256(data).hexdigest()
assert digest == verification['kernel_sha256'] == progress['kernel_sha256']
assert progress['desktop_verified']
assert data[:4] == bytes.fromhex('cffaedfe')
machine = command[command.index('-machine') + 1]
cpu = command[command.index('-cpu') + 1]
assert machine.startswith('virt,') and cpu.startswith('cortex-a76')
previous = json.loads((root / 'outputs/MIX4-UniXNU-core-u08/device-outcome.json').read_text())
previous_manifest = json.loads((root / 'outputs/MIX4-UniXNU-core-u08/manifest.json').read_text())
assert not previous['os_root_included']
physical_replay = json.loads((dev / 'build/qemu-early-entry-u63physicaldtirq/verification.json').read_text())
native_manifest = json.loads((root / 'outputs/MIX4-UniXNU-desktop-u65/manifest.json').read_text())
native_image = root / 'outputs/MIX4-UniXNU-desktop-u65' / native_manifest['artifact']
assert hashlib.sha256(native_image.read_bytes()).hexdigest() == native_manifest['sha256']
last_native = json.loads((root / 'outputs/MIX4-UniXNU-desktop-u64/runs/20261104-212509/result.json').read_text())
assert physical_replay['halted_before_symbol'] == '_pe_arm_init_interrupts'
assert not physical_replay['qemu_hardware_overlay'] and not physical_replay['qemu_vmm_present']
assert physical_replay['source_adt_sha256'] == physical_replay['replay_adt_sha256']
report = dict(
    flash_ready=False,
    host_icon_desktop_verified=True,
    device_commands_executed=False,
    partition_writes_executed=False,
    kernel_sha256=digest,
    kernel_format='ARM64 Mach-O, not an Android boot image',
    qemu_machine=machine,
    qemu_cpu=cpu,
    qemu_hardware_overlay=verification['qemu_hardware_overlay'],
    qemu_vmm_present=verification['qemu_vmm_present'],
    system_ramdisk_bytes=verification['ramdisk_bytes'],
    desktop_release_boot_images=[p.name for p in release.glob('*boot*.img')],
    native_desktop_candidate=dict(artifact=str(native_image), sha256=native_manifest['sha256'],
        system_supplied_over_usb=True, requires_host_media_server=True, hardware_qualified=False),
    u64_physical_media_bytes_served=last_native['bytes_served'],
    previous_phone_candidate=dict(
        artifact=previous_manifest['artifact'],
        os_root_included=previous['os_root_included'],
        before_pe_init_platform_reached=previous['before_pe_init_platform_reached'],
        pe_init_platform_returned_confirmed=previous['pe_init_platform_returned_confirmed'],
        full_ios_desktop_confirmed=previous['full_ios_desktop_confirmed']),
    physical_adt_cpu_replay=dict(
        early_pe_init_platform_returned=True,
        reached_before='_pe_arm_init_interrupts',
        device_tree_unchanged=True,
        actual_phone_runtime_qualified=False),
    blockers=[
        'u65 phone boot image with USB-backed u62 payload is built; physical USB enumeration and transfer remain unqualified',
        'u62 runtime qualification used QEMU virt hardware and virtual GIC, not odin hardware',
        'Last physical-device markers end before PE_init_platform; the failing physical instruction is unknown, not a proven PE function hang',
        'Physical scanout, native ST input and A660 are not qualified for this UniXNU kernel'],
    next_required_work='Recover Android to load u65; qualify USB system/media handoff, physical kernel initialization and scanout',
    action='Do not flash the QEMU Mach-O or substitute the old u08 diagnostic image')
assert not report['desktop_release_boot_images']
output = build / 'device-flash-readiness.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
