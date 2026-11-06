"""Record the completed GitHub review and publish u02's local audit bundle."""
from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parents[1]
RESEARCH = PORT / 'research/github-20261103'
RELEASE = ROOT / 'outputs/MIX4-UniXNU-core-u02'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = read(RELEASE / 'manifest.json')
assert sha(RELEASE / manifest['artifact']) == manifest['sha256']
assert manifest['adt']['gicr_bytes'] == 0x100000
assert manifest['adt']['hardware_interrupt_cells'] == 3
assert manifest['retained_exact_ffs_count'] == 141
assert not manifest['device_tested']

findings = {
    'qine233/UniXNU-odin': 'MIX 4 板级参考；输入仅有主机验证，GPU 为 PM4/电源观察层，尚无可直接使用的完整系统镜像。',
    'qine233/uefi-odin': '固件平台参考；仍需板级输入，不能替换本地已亮屏的固件基线。',
    'qine233/UniXNU-sm8350-common': 'SM8350 资源与多核 affinity 参考；本轮交叉核对真实 FDT，候选仍用单 CPU。',
    'UniXNU/UniXNU': '新 HEAD 比本地构建 pin 多 24 个提交，包含显示同步和 Metal 相关更新；本轮未把整个框架切到新 HEAD。',
    'UniXNU/AdrenoMetal': '前端 GPU 合成验收范围为 sheng/A740；还依赖内核 GPU ABI 和 Turnip，不能视为 A660 已可用。',
    'OddlyLabs/FuxiFtsTouch': '同为 ST FTM5，ID 36 40，含 FIFO dummy 和高分辨率 LE16 解码；两个原有主机测试通过，两个模块成功编译为 arm64 iOS16.5 对象，未链接内核。',
    'OddlyLabs/unixnu-fuxi': '有实机 ID/触点证据和独立采集/HID 线程结构；其 HID ABI 绑定 iPadOS17，必须重新提取 iOS16.5 ABI，不能复制地址和类布局。',
    'xuanli-cn/UniXNU-lemonadep': '本次固定版本只有 README，没有可直接移植的实现。',
    'UniXNU/GopFramebuffer': '新 fence 等待修补：busy/unknown/慢完成时保留旧帧和首次目标，完成或取消后再推进；原有真实方法主机测试通过，尚未移植到本地16.5候选。',
}
sources = []
for receipt_path in sorted(RESEARCH.glob('*-receipt.json')):
    receipt = read(receipt_path)
    assert sha(RESEARCH / receipt_path.name.replace('-receipt.json', '.tar.gz')) == receipt['sha256']
    sources.append({**receipt, 'review': findings[receipt['repo']],
                    'commit_url': f"https://github.com/{receipt['repo']}/tree/{receipt['commit']}"})
assert len(sources) == 9

gop = next(s for s in sources if s['repo'] == 'UniXNU/GopFramebuffer')
gop_root = ROOT / gop['source_root']
gop_test = {
    'repository': gop['repo'], 'commit': gop['commit'],
    'command': 'python3 Test/check-fence-wait.py',
    'environment': 'existing x86_64 Linux build VM',
    'status': 'PASS',
    'stdout': 'PASS: actual display methods defer busy/unknown/slow fences, preserve targets and clear cancelled waits',
    'record_origin': 'Completed execution observed earlier in this build turn; recorded here without rerunning',
    'scope': 'Actual NativeLegacyDisplay.cpp methods extracted by upstream test; fake GPU, ASan/UBSan. No physical GPU or display validation.',
    'inputs': {p: sha(gop_root / p) for p in ['Test/check-fence-wait.py', 'NativeLegacyDisplay.cpp']},
    'linked_into_u02': False, 'device_tested': False,
}
write(RESEARCH / 'host-checks/gop-fence-verification.json', gop_test)
review = {
    'updated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'sources': sources,
    'applied_to_u02': {
        'gicr_bytes': 0x100000, 'hardware_interrupt_cells': 3,
        'evidence': 'build/native-payload/hardware-evidence.json',
        'basis': 'MIX4 saved live FDT, not another device board constants',
    },
    'touch_tests': 'host-checks/verification.json',
    'display_tests': 'host-checks/gop-fence-verification.json',
    'next_integration': 'iOS16.5 original IOHIDFamily ABI extraction and original kext prelink before native HID service integration',
    'device_commands_executed': False, 'device_tested': False,
}
write(RESEARCH / 'review.json', review)
report = '''# GitHub 源码复核与 u02 变更

本轮下载并固定了 9 个仓库的提交；每个 archive 均保存 SHA256 和来源 receipt。没有向手机发送命令。

## 已落实到镜像

对照 SM8350 社区资料后，以 MIX 4 保存的真实 FDT 为准，修正 GICR 范围为 `0x17a60000 + 0x100000`，硬件中断描述为 3 单元；生成脚本加入原始 FDT 断言。u02 的最终 ADT 独立解码检查通过。

u02 保留亮屏基线的 141 个 FFS 完整字节。FAT 四文件回读和 boot v3 各段检查通过。

## 参考项目与适用范围

'''
for source in sources:
    report += f"- [{source['repo']}]({source['commit_url']})：{source['review']}\n"
report += '''
## 验证范围

- FuxiFtsTouch 的原有 `fts-protocol`、`touch-core` 测试通过；`FtsProtocol.c` 和 `FtsTouchCore.c` 成功编译为 arm64 iOS16.5 Mach-O 对象。未链接进内核，未接板级总线或 HID。
- GopFramebuffer 原有 `python3 Test/check-fence-wait.py` 在现有 Linux VM 通过。该测试执行实际显示方法，使用模拟 GPU 和 ASan/UBSan；不验证手机 GPU 或实体屏幕。
- 不把别的仓库的 README、主机测试、编译成功当作 MIX 4 实机验收。触摸端点和过滤规则保留本地实测约束。

## 当前产物与下一步

`outputs/MIX4-UniXNU-core-u02/` 为原生 XNU 内核入口 RAM 临时启动候选，仍使用 iOS16.5 / 20F66，未实机测试。没有原始 Apple kext prelink、OS root、原生 HID worker 或 A660 Metal，不能进入完整 iOS 桌面。

下一步优先核对 iOS16.5 原始 IOHIDFamily ABI 并补齐 prelink，再接入独立采集/HID 线程。fuxi 的 iPadOS17 类布局和地址不能直接复用。显示 fence 修补待 ABI 和显示组件适配后再接入。

详细提交、archive 哈希、测试对象和硬件来源见 `review.json` 与 `host-checks/`。本轮没有修改 u01 归档。
'''
(RESEARCH / 'REVIEW.md').write_text(report, encoding='utf-8')

status = read(PORT / 'migration-status.json')
status.update(updated_at=review['updated_at'],
              phase='u02 RAM-boot candidate host audited; live-FDT GIC corrected; GitHub touch/display references reviewed; device test pending',
              release_manifest='outputs/MIX4-UniXNU-core-u02/manifest.json',
              image_sha256=manifest['sha256'],
              github_review='research/github-20261103/review.json',
              measured_gicr_bytes=0x100000, measured_interrupt_cells=3)
write(PORT / 'migration-status.json', status)
pins = read(PORT / 'source-pins.json')
pins['native_candidate'].update(release='u02', image_sha256=manifest['sha256'])
pins['github_review_sources'] = [
    {'repository': s['repo'], 'commit': s['commit'], 'archive_sha256': s['sha256'],
     'scope': s['review'], 'included_in_native_kernel': False} for s in sources
]
pins['github_review'] = 'research/github-20261103/review.json'
write(PORT / 'source-pins.json', pins)
readme_path = PORT / 'README.md'
readme = readme_path.read_text(encoding='utf-8').replace('MIX4-UniXNU-core-u01', 'MIX4-UniXNU-core-u02').replace('core-u01-boot.img', 'core-u02-boot.img')
readme = readme.replace('`scripts/package_core_image.py`，', '`scripts/package_core_image.py --release u02`，')
readme += '''
## GitHub 复核（2026-11-03）

已固定下载 9 个参考项目，详情见 `research/github-20261103/REVIEW.md`。u02 依据真实 odin FDT 修正 GICR 为 1 MiB 和硬件中断 3 单元。Fuxi ST 协议测试、iOS16.5 对象编译及最新 GOP fence 主机测试通过；这些触摸/显示参考模块尚未接入候选，未验证实体触摸或 A660 Metal。
'''
readme_path.write_text(readme, encoding='utf-8')

evidence = RELEASE / 'evidence'
evidence.mkdir(exist_ok=True)
paths = [
    'build/boot-abi/verification.json', 'build/firmware/verification.json',
    'build/initrd-prefix-test/verification.json', 'build/native-payload/fat-verification.json',
    'build/native-payload/kernel-audit.json', 'build/native-payload/hardware-evidence.json',
    'build/qemu-menu/verification.json', 'migration-status.json', 'source-pins.json',
    'research/github-20261103/review.json',
    'research/github-20261103/host-checks/verification.json',
    'research/github-20261103/host-checks/gop-fence-verification.json',
]
for path in paths:
    shutil.copyfile(PORT / path, evidence / path.replace('/', '--'))
shutil.copyfile(RESEARCH / 'REVIEW.md', RELEASE / 'GitHub-review.md')
write(evidence / 'index.json', {
    'artifact_sha256': manifest['sha256'],
    'files': {p.name: sha(p) for p in sorted(evidence.iterdir()) if p.is_file() and p.name != 'index.json'},
    'device_tested': False,
})
print(json.dumps({'release': str(RELEASE), 'bytes': manifest['bytes'],
                  'image_sha256': manifest['sha256'], 'reviewed_repositories': len(sources),
                  'evidence_files': len(paths), 'device_commands_executed': False}, ensure_ascii=False))
