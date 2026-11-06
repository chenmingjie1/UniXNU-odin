"""Archive exact host display evidence; never claim desktop from frame counters."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import tarfile

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', required=True)
p.add_argument('--build-tag', required=True)
p.add_argument('--output-tag')
p.add_argument('--desktop-frame', type=Path,
               help='Explicit manually inspected icon-home screenshot from this replay; never inferred from logs')
p.add_argument('--extra-evidence', type=Path, action='append', default=[],
               help='Additional audit JSON/text file or directory; original executables are not copied')
a = p.parse_args()
assert a.tag.isalnum() and a.build_tag.isalnum()
output_tag=a.output_tag or a.build_tag
assert output_tag.isalnum()
run = DEV / ('build/qemu-early-entry-' + a.tag)
build = DEV / ('build/display-owner-' + a.build_tag)
out = ROOT / ('outputs/MIX4-UniXNU-display-' + output_tag)
assert not out.exists(), 'Preserve previous evidence'
analysis = json.loads((run / 'desktop-runtime-analysis.json').read_text())
assert not analysis['device_commands_executed']

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

assert digest(build / 'kernel.prelinked.experimental.macho') == analysis['kernel_sha256']
out.mkdir()
runtime = out / 'runtime'
runtime.mkdir()
for name in ('verification.json', 'desktop-runtime-analysis.json', 'framebuffer.png',
             'printf.json', 'panic.json', 'register-observations.json', 'command.json',
             'symbol-_odin_surface_inspections.bin', 'logical-pm-analysis.json',
             'userspace-live.log', 'display-live.jsonl', 'replay.adt', 'periodic-frames.jsonl',
             'user-fatal-live.jsonl', 'ui-thread-snapshot.json', 'ui-thread-analysis.json', 'ui-thread-plan.json',
             'data-log-live.jsonl', 'host-input-final.log', 'own-component-final-logs.json',
             'registers.json'):
    source = run / name
    if source.is_file():
        shutil.copy2(source, runtime / name)
for source in run.glob('copied-frame-*.png'):
    shutil.copy2(source, runtime / source.name)
for source in run.glob('periodic-frame-*.png'):
    shutil.copy2(source, runtime / source.name)
for source in run.glob('ui-thread-periodic-*.json'):
    shutil.copy2(source, runtime / source.name)
extra = out / 'input-audits'
for requested in a.extra_evidence:
    requested = requested.resolve()
    requested.relative_to(DEV)
    assert requested.exists(), requested
    files = list(requested.rglob('*')) if requested.is_dir() else [requested]
    for source in files:
        if source.is_file() and source.suffix in ('.json', '.txt', '.md'):
            target = extra / source.relative_to(DEV)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
audit = out / 'build-audit'
audit.mkdir()
for name in ('compile-receipt.json', 'interface-compiler-audit.json',
             'display-link-audit.json', 'independent-audit.json',
             'prelink-emission-report.json', 'display-observer-contract.json'):
    source = build / name
    if source.is_file():
        shutil.copy2(source, audit / name)
archive = out / 'display-source.tar.gz'
sources = list((build / 'source').glob('*')) + [build / 'original-bindings.S']
sources += [DEV / 'scripts' / name for name in (
    'prepare_odin_display_interface.py', 'build_odin_display_owner.py',
    'check_odin_display_interface.py', 'link_host_display_candidate.py',
    'audit_odin_display_link.py', 'audit_ios16_display_queue.py',
    'run_u15_host_display.ps1', 'qemu_early_entry.py',
    'analyze_host_desktop_runtime.py', 'summarize_logical_display_pm.py',
    'archive_display_cpu_progress.py', 'inspect_root_exec.py',
    'prepare_observed_service_trust.py', 'build_development_trust.py',
    'prepare_launch_services_root.py', 'prepare_host_network_adt.py',
    'audit_mobileactivation_trap.py', 'audit_root_macho_catalog.py',
    'audit_host_data_checkpoint.py', 'expand_host_data_checkpoint.py',
    'audit_standalone_runtime_traps.py', 'audit_migration_preference_contract.py',
    'audit_thread_snapshot_layout.py', 'ui_thread_observer.py', 'analyze_ui_thread_snapshot.py',
    'prepare_upstream_setup_preferences.py', 'build_host_virtual_input.py',
    'prepare_host_virtual_input_root.py', 'prepare_host_sleep_adt.py',
    'install_host_sb_exec.py', 'install_host_sb_dyld_policy.py')]
sources += [build / name for name in ('host-sb-exec.patch', 'host-sb-exec-receipt.json',
    'host-sb-dyld.patch', 'host-sb-dyld-receipt.json')]
sources += list((DEV / 'host-input').glob('*'))
sources += [DEV / 'research/github-display-20261104' / name
            for name in ('sources.json', 'FINDINGS.md', 'heads-recheck.json')]
sources += [DEV / 'build/display-analysis-ios16' / name for name in (
    'u31-queue-contract.json', 'u31-queue-move.txt', 'u31-submit-queue-contract.txt')]
with tarfile.open(archive, 'w:gz') as tar:
    for source in sources:
        if source.is_file():
            tar.add(source, arcname=source.relative_to(ROOT))
record = dict(updated_at=datetime.now(timezone.utc).isoformat(),
    scope='Computer-only UniXNU iOS16.5 CPU display; not a phone boot image',
    build_tag=a.build_tag, run_tag=a.tag, kernel_sha256=analysis['kernel_sha256'],
    surface_inspection=analysis['surface_inspection'], panic=analysis['panic'],
    original_pm_callback_verified=any('logical PM callback' in row['format']
        and row['slots'][:5] == [1, 0, 1, 1, 0] for row in analysis['provider_logs']),
    presentation_implemented=analysis['presentation_implemented'],
    desktop_verified=False, device_commands_executed=False,
    source_archive=dict(file=archive.name, sha256=digest(archive)),
    raw_trace=dict(path=str((run / 'trace.log').relative_to(ROOT)),
                   sha256=analysis['trace_sha256']))
if a.desktop_frame:
    frame = a.desktop_frame.resolve()
    assert frame.parent == run.resolve() and frame.suffix == '.png' and frame.is_file()
    assert not analysis['panic']
    assert (runtime / frame.name).is_file()
    record['desktop_verified'] = True
    record['desktop_visual_evidence'] = dict(
        file='runtime/' + frame.name, sha256=digest(frame),
        method='Explicit visual inspection: application icon grid and Dock, not a lockscreen or method return',
        scope='Host QEMU CPU presentation only; physical display, touch and A660 unverified')
verification = json.loads((run / 'verification.json').read_text())
record['input_contract'] = {key: verification[key] for key in (
    'source_adt_sha256', 'replay_adt_sha256', 'ramdisk_bytes',
    'data_ramdisk_bytes', 'data_ramdisk_sha256', 'trust_cache_sha256',
    'boot_args', 'observation_seconds', 'owned_memory_size') if key in verification}
record['signature_rejections'] = analysis['signature_rejections']
record['launch_services'] = analysis['launch_services']
(out / 'progress.json').write_text(json.dumps(record, indent=2) + '\n')
status_path = DEV / 'migration-status.json'
status = json.loads(status_path.read_text())
status.update(updated_at=record['updated_at'],
    phase='Host-only ' + output_tag + (': actual icon desktop visually confirmed' if record['desktop_verified'] else ': captured kernel panic; desktop unverified' if analysis['panic']
        else ': CPU presentation/service runtime evidence; desktop unverified'),
    host_selected_kernel=str((build / 'kernel.prelinked.experimental.macho').relative_to(ROOT)),
    host_selected_kernel_sha256=record['kernel_sha256'],
    host_evidence=str((out / 'progress.json').relative_to(ROOT)),
    host_new_boot_image_created=False, latest_host_candidate_device_tested=False,
    full_ios_desktop_confirmed=False, device_commands=False,
    host_icon_desktop_verified=record['desktop_verified'],
    host_cpu_presentation=record['surface_inspection'])
status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + '\n')
(out / 'manifest.json').write_text(json.dumps({str(path.relative_to(out)): digest(path)
    for path in out.rglob('*') if path.is_file()}, indent=2) + '\n')
print(json.dumps(record, indent=2))
