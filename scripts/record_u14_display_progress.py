"""Save source/compile evidence while keeping u13 runtime claims unchanged."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import tarfile

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
BUILD = DEV/'build/display-analysis-ios16'
OUT = ROOT/'outputs/MIX4-UniXNU-display-u14'
OUT.mkdir(exist_ok=True)
compiler = json.loads((BUILD/'interface-compiler-audit.json').read_text())
protocol = json.loads((BUILD/'protocol-static-audit.json').read_text())
assert compiler['checked_slots'] == compiler['backend_checked_slots'] == 338
assert not compiler['linked'] and not compiler['executed']
assert protocol['selector_count'] == 87 and protocol['rows_preserved_from_original']
assert compiler['candidate_sha256'] == protocol['candidate_sha256']
scripts = ['audit_odin_display_abi.py', 'audit_odin_display_protocol.py',
    'prepare_odin_display_interface.py', 'compile_odin_display_annotation.py',
    'check_odin_display_interface.py', 'disassemble_odin_display.py',
    'record_u14_display_progress.py']
files = [DEV/'scripts'/name for name in scripts]
files += sorted(p for p in (DEV/'drivers/OdinDisplay').iterdir() if p.is_file())
files += sorted(p for p in BUILD.iterdir() if p.is_file() and p.suffix in ('.json','.txt','.o','.S','.log'))
for name in ('interface-compiler-audit.json','protocol-static-audit.json','compile-receipt.json'):
    (OUT/name).write_bytes((BUILD/name).read_bytes())
archive = OUT/'odin-display-u14-source-and-compile.tar.gz'
with tarfile.open(archive,'w:gz') as stream:
    for path in files:
        stream.add(path,arcname=path.relative_to(ROOT).as_posix())
record = dict(updated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    scope='Computer-only source and compiler checks; neither a runtime kernel nor a phone boot image',
    target_os='iOS 16.5 / 20F66', last_runtime_progress='outputs/MIX4-UniXNU-host-u12/progress.json',
    runtime_kernel_sha256=compiler['candidate_sha256'],
    original_family_text_sha256=compiler['original_family_text_sha256'],
    qualified_original_class_bytes=0x1660, qualified_original_entries=338,
    qualified_userclient_selectors=87, qualified_abstract_slots=compiler['abstract_leaves'],
    annotation_compiled=True, gop_mapping_backend_compiled=True,
    compiler_flags=['-Wall','-Wextra','-Werror'],
    annotation_dispatch_entries_checked=338, backend_dispatch_entries_checked=338,
    dispatch_structure_bytes=24, external_arguments_bytes=248,
    original_selector_rows_preserved=87, dimension_fields=protocol['dimension_fields'],
    hardware_start_slot=274, provider_pre_dispatch_slot=182,
    linked=False, executed=False, display_published=False, frames_presented=False,
    desktop_verified=False, physical_display_verified=False,
    a660_metal_verified=False, native_touch_verified=False,
    device_commands_executed=False, new_phone_boot_image_created=False,
    qemu_replay_repeated=False,
    blockers=['Qualify main-display identity and discovery for the actual iOS16 ABI',
        'Adapt original IOSurface backing and display swap/retirement/refresh contracts',
        'Add startup integration only after backend contracts are implemented',
        'Verify actual rendered desktop in host QEMU; phone platform/HID/A660 remain separate'],
    archive=dict(path=archive.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(archive.read_bytes()).hexdigest()),
    files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
(OUT/'progress.json').write_text(json.dumps(record,indent=2)+'\n')
status_path=DEV/'migration-status.json'
status=json.loads(status_path.read_text())
status['updated_at']=record['updated_at']
status['phase']='Host-only: iOS16 display ABI and GOP mapping source compile checked; display registration/presentation incomplete'
status['display_u14']=dict(evidence='outputs/MIX4-UniXNU-display-u14/progress.json',
    original_entries=338, original_bytes=0x1660, selectors=87,
    gop_mapping_compiled=True, linked=False, executed=False, desktop_verified=False,
    device_commands_executed=False)
status_path.write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
(OUT/'README.md').write_text('''本轮只做电脑端显示适配，没有查询或操作 MIX 4。

已经从实际 iOS16.5 / 20F66 驱动核对 Legacy 的 338 个入口、0x1660 字节
实例及 87 个用户客户端命令；现有 iPadOS17 的 358 / 0x18a0 / 90 不能直接复用。
确认构造/析构继承链、原始命令表、尺寸字段和显示启动入口。

新增 GOP 映射代码和版本匹配的接口头。两个对象用实际内核编译参数通过严格警告检查，
独立比较其全部 338 个入口；编译器同时检查客户端参数结构及字段偏移。

这两个对象尚未链接或运行。主显示识别、IOSurface 帧传输、完成通知和注册接入仍待实现。
u13 的桌面进程仍因缺少主 CADisplay 退出；本轮没有新的桌面运行结果。
原有内核、系统盘及 u13 运行证据保留；没有制作新的手机镜像。

精确文件哈希、编译收据、源码和静态核对见 progress.json 及归档。
''',encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k != 'files'},indent=2))
