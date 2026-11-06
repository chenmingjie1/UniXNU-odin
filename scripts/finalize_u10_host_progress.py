"""Record reproducible host-only progress without promoting it to phone success."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import shutil
import struct

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', required=True)
parser.add_argument('--kernel-dir', default='ios16-prelink-u10cs')
args = parser.parse_args()
assert args.run.isalnum()
assert args.kernel_dir.replace('-', '').isalnum()
kernel_dir = DEV/'build'/args.kernel_dir
run = DEV/('build/qemu-early-entry-'+args.run)
out = ROOT/'outputs/MIX4-UniXNU-host-u10'
out.mkdir(parents=True, exist_ok=True)
load = lambda path: json.loads(path.read_text())
relative = lambda path: path.relative_to(ROOT).as_posix()

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

replay = load(run/'verification.json')
logs = load(run/'printf.json')
calls = load(run/'syscalls.json') if (run/'syscalls.json').exists() else []
audit = load(kernel_dir/'independent-audit.json')
maps = load(DEV/'build/root-media/system-resource-maps-u10.json')
media = load(run/'loaded-media.json')
assert audit['passed'] and audit['candidate_sha256'] == replay['kernel_sha256']
assert all(row['matches_input'] for row in media)
assert maps['all_other_image_bytes_identical'] and maps['maps_repaired'] == 8340
formats = [row.get('format') or '' for row in logs]
assert any('BSD root:' in line for line in formats)
assert any('owner development entry' in line for line in formats)
first_el0 = None
last_el0 = None
el0_returns = 0
with (run/'trace.log').open(errors='replace') as stream:
    for line in stream:
        if 'Exception return from AArch64 EL1 to AArch64 EL0 PC ' in line:
            first_el0 = first_el0 or line.strip()
            last_el0 = line.strip()
            el0_returns += 1
assert first_el0 and calls, 'Do not claim user-mode execution without actual EL0/syscall evidence'
panic = load(run/'panic.json') if (run/'panic.json').exists() else None
signature_counters = {}
for name in ('_cs_native4k_ready_blobs','_cs_native4k_full_blocks','_cs_native4k_bytes'):
    snapshot = run/('symbol-'+name+'.bin')
    if snapshot.exists():signature_counters[name] = struct.unpack_from('<Q',snapshot.read_bytes())[0]
user_log = ''.join(row.get('write_text', '') for row in calls)
launchd_bootstrap = ('Darwin Bootstrapper Version 7.0.0' in user_log and
                    'Early boot complete. Continuing system boot.' in user_log)
missing_services = [line for line in user_log.splitlines()
                    if 'Failed to bootstrap path:' in line or 'Unable to open /System/Library/xpc/launchd.plist' in line]
all_caches_ready = (signature_counters.get('_cs_native4k_ready_blobs') == 43 and
                    signature_counters.get('_cs_native4k_full_blocks') == 165818)
trust_candidates = [DEV/'build/root-media/cache-development-trust-u10.bundle',
                    DEV/'build/root-media/dynamic-launchd-audit/development-trust.bundle']
trust_path = next(path for path in trust_candidates if path.exists() and digest(path) == replay['trust_cache_sha256'])
cache_audit = load(DEV/'build/root-media/dyld-cache-audit-u10.json')
assert len(cache_audit) == 43
assert all(not cd['page_hash_mismatches'] for row in cache_audit for cd in row['code_directories'])
files = [kernel_dir/'kernel.prelinked.experimental.macho',
         kernel_dir/'native-real-iig.macho',
         DEV/'build/root-media/system-resource-maps-u10.apfs',
         trust_path,
         DEV/'build/native-kernel/odin-desktop-u10-final-evidence.tar.gz']
record = {
    'updated_at': datetime.now().astimezone().isoformat(),
    'workspace_root': str(ROOT),
    'scope': 'Host QEMU Cortex-A76 replay only; not SM8350 qualification',
    'target_os': 'iOS 16.5 / 20F66',
    'device_commands_executed': False, 'new_phone_boot_image_created': False,
    'full_system_apfs_mount_verified': True,
    'development_trust_modules_loaded': any('loaded external trust cache module' in s for s in formats),
    'original_kext_text_preserved': len(audit['original_executable_kexts_byte_identical']),
    'prelink_pointers_checked': audit['actual_pointer_values_checked'],
    'resource_maps_repaired': maps['maps_repaired'],
    'dyld_cache_files_audited': len(cache_audit),
    'dyld_cache_signature_pages_verified': sum(cd['code_slots'] for row in cache_audit for cd in row['code_directories']),
    'guest_signature_validation_counters':signature_counters,
    'pid1_dyld_el0_execution_verified': True, 'el0_returns': el0_returns,
    'first_el0': first_el0, 'last_el0': last_el0,
    'shared_cache_runtime_validation_complete': all_caches_ready,
    'launchd_main_verified': launchd_bootstrap, 'desktop_verified': False,
    'launchd_main_evidence': 'Actual userspace write syscalls: Darwin Bootstrapper banner and Early boot complete' if launchd_bootstrap else None,
    'missing_service_paths': missing_services,
    'native_touch_verified': False, 'a660_metal_verified': False,
    'replay': relative(run/'verification.json'),
    'syscalls': relative(run/'syscalls.json'), 'last_syscalls': calls[-8:],
    'panic': panic,
    'inputs': [{'path':relative(p),'bytes':p.stat().st_size,'sha256':digest(p)} for p in files],
    'remaining': [
        ('Restore missing /redwood/LaunchDaemons configurations, supply writable Data, then start desktop services'
         if launchd_bootstrap else 'Complete shared-cache loading and observe launchd main, then actual desktop services'),
        'Device PE_init_platform / iOS16.5 PMGR provider and >2.48GB reserved root loading',
        'Native MIX4 MobileFramebuffer, ST HID worker and A660 Metal integration'],
}
(out/'progress.json').write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
(out/'launchd-userspace.log').write_text(user_log, encoding='utf-8')
for source, target in [(run/'verification.json','replay.json'), (run/'printf.json','printf.json'),
                       (run/'syscalls.json','syscalls.json'),
                       (kernel_dir/'independent-audit.json','prelink-audit.json'),
                       (DEV/'build/root-media/system-resource-maps-u10.json','resource-map-repair.json'),
                       (DEV/'build/root-media/dyld-cache-audit-u10.json','cache-signature-audit.json')]:
    shutil.copyfile(source, out/target)
state_path = DEV/'migration-status.json'
state = load(state_path)
state.update({
    'updated_at':record['updated_at'],
    'phase':('Host-only: all 43 shared caches validated and launchd userspace bootstrap completes; desktop not verified'
             if launchd_bootstrap else 'Host-only: full APFS mounted, dynamic PID1 dyld executes at EL0; desktop not verified'),
    'device_commands':False,
    'host_selected_kernel':(kernel_dir/'kernel.prelinked.experimental.macho').relative_to(DEV).as_posix(),
    'host_selected_kernel_sha256':replay['kernel_sha256'],
    'host_root_mount_verified':True, 'host_full_system_root_bytes':2476732416,
    'host_pid1_dyld_el0_verified':True, 'host_launchd_main_verified':launchd_bootstrap,
    'host_shared_cache_runtime_validation_complete':all_caches_ready,
    'host_evidence':relative(out/'progress.json'),
    'host_resource_maps_repaired':8340,
    'host_new_boot_image_created':False, 'latest_host_candidate_device_tested':False,
    'full_ios_desktop_confirmed':False,
    'blockers':record['remaining'],
})
state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n', encoding='utf-8')
readme = DEV/'README.md'
history = DEV/'README-core-u03-historical.md'
if not history.exists():shutil.copyfile(readme,history)
readme.write_text('''# MIX 4 → UniXNU

## 当前状态（2026-11-04，电脑端）

完整 iOS16.5 / 20F66 APFS 系统盘已在 QEMU 中由原始 Apple APFS 驱动挂载。
显式选择 `/sbin/launchd.ios` 后，PID1 的 dyld 已实际进入 ARM64 EL0 并发出系统调用。
''' + ('43 个共享缓存已在运行时完成 165,818 个原始签名块核验；launchd 已实际输出版本信息和“Early boot complete”。\n'
       '当前启动止于系统服务配置：`/System/Library/LaunchDaemons` 指向未挂载的 `/redwood/LaunchDaemons`。\n'
       '**尚未证明 SpringBoard 或桌面启动成功，不能上机作为桌面镜像。**\n'
       if launchd_bootstrap else '**尚未证明 launchd main、SpringBoard 或桌面启动成功，不能上机作为桌面镜像。**\n') + '''

遵守用户“你不让我进桌面就不要动我手机”的要求：本轮没有 ADB、fastboot、
设备查询、重启或刷写，也没有生成新的手机 boot.img。QEMU 的硬件树、VMM 标记
和大内存窗口仅用于电脑回放，不是 SM8350 驱动或真实手机内存分配结果。

## 已修复并留存证据

- BCM2837 构建被 SDK 兼容头误标成 Apple 平台，导致大内存时 4K/16K 页合同冲突；已修复并验证完整 2,476,732,416 字节根盘挂载。
- 旧静态 `/sbin/launchd` 没有 dyld vnode，不能直接复用它的启动链。新增仅 DEVELOPMENT 的显式 `odin-init-path=/sbin/launchd.ios`，保留正常 exec/AMFI 检查。
- 原始 AppleFSCompression 对资源映射表进行 50 字节固定比较。修正副本中 8,340 个合成压缩文件的 16 字节冗余表头，其他镜像字节逐字节一致；关键文件代码页哈希再次通过。
- 支持 PAN 的 Cortex-A76/SM8350 需要相应 copyin/out 处理；已启用 PAN 并将编译目标调整为 ARMv8.1。保留失败编译、宏检查、成功构建和回放证据。
- 43 个共享缓存文件的原始签名代码页全部通过独立审计。开发信任表只包含已审计文件的 cdhash（具体输入见统一证据）；这是本机所有者开发信任，不是 Apple attestation。30 个原始 kext text 保持字节一致，65,319 个指针独立校验通过。
- 显式开发启动可发布既有 `dyld_flags`、指定实际 Cryptex 缓存目录；启用上游先核验原始 16K 签名、再派生 4K 页哈希的兼容路径，未关闭 AMFI。

## 当前产物与复现入口

- 统一证据：`../../outputs/MIX4-UniXNU-host-u10/progress.json`（路径以工作区为准）。
- 内核：`build/ios16-prelink-u10cs/kernel.prelinked.experimental.macho`。
- 修复系统盘：`build/root-media/system-resource-maps-u10.apfs`。
- 状态：`migration-status.json`；实时阻塞、实际启动参数和系统调用见统一证据引用的 replay/syscalls。
- 构建：`scripts/build_offline_kernel.sh`、`scripts/link_offline_kernel.sh`；XNU 修补清单：`patches/xnu/series`。
- 系统盘修复：`scripts/repair_mkapfs_spaceman.py`、`scripts/repair_mkapfs_resource_maps.py`；后续打包工具修补：`patches/root-media/`。
- 可执行文件审计及信任：`scripts/inspect_root_exec.py`、`scripts/build_development_trust.py`。
- 电脑回放：`scripts/qemu_early_entry.py`；`--syscall-log` 只读取实际保存的 ARM64 syscall 状态，不改内核指令。

## 尚未完成

桌面服务配置及可写 Data 卷、SpringBoard；真机 PMGR/platform 和大根盘连续内存交接；
UniXNU 原生显示、ST HID 与 A660 Metal。旧 HakiOS 的桌面、触摸和 GPU 实测不能算作 UniXNU 验收。
历史 core-u03 构建细节保存在 `README-core-u03-historical.md`。
本目录未发布到远端，既有源代码及复用组件保留原始许可。
''', encoding='utf-8')
print(json.dumps({k:record[k] for k in ('scope','full_system_apfs_mount_verified',
    'pid1_dyld_el0_execution_verified','launchd_main_verified','desktop_verified','el0_returns')},indent=2))
