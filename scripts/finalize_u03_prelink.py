"""Publish the local prelinked u03 candidate and its bounded verification evidence."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import shutil
import tarfile
import tomllib

DEV=Path(__file__).resolve().parents[1]
ROOT=DEV.parents[1]
BUILD=DEV/'build/ios16-prelink'
RELEASE=ROOT/'outputs/MIX4-UniXNU-core-u03'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

m=read(RELEASE/'manifest.json')
a=read(BUILD/'independent-audit.json')
assert m['sha256']==sha(RELEASE/m['artifact'])
assert m['original_kexts_prelinked'] and a['passed']
assert m['kernel_audit']['sha256']==a['candidate_sha256']
assert not m['complete_ios_system'] and not m['device_tested']
now=datetime.now(timezone(timedelta(hours=8))).isoformat()
status=read(DEV/'migration-status.json')
status.update(updated_at=now,
    phase='u03 with real IIG RPC and 30 original Apple executable kexts prelinked; byte audits pass; OS root and native HID pending',
    original_kexts_prelinked=True, release_manifest='outputs/MIX4-UniXNU-core-u03/manifest.json',
    image_sha256=m['sha256'], real_driverkit_iig_implementations=17, iorpc_bytes=24,
    prelink_independent_audit='build/ios16-prelink/independent-audit.json',
    original_kexts_runtime_qualified=False,
    current_device_state='Not queried or operated this turn; no device state inferred from computer builds')
status['blockers']=[
    'Actual odin firmware / DarwinBoot / prelinked-XNU handoff and original kext startup validation',
    'OS root integration and runtime validation of original iOS16.5 services',
    'Measure iOS16.5 IOHIDDevice ABI; link native ST bus, worker and HID lifecycle',
    'Adreno660 native rendering and display synchronization qualification']
write(DEV/'migration-status.json',status)
pins=read(DEV/'source-pins.json')
pins['native_candidate'].update(release='u03', image_sha256=m['sha256'],
    native_kernel_sha256=a['native_sha256'], prelinked_kernel_sha256=a['candidate_sha256'],
    original_kernelcache_sha256=a['original_sha256'], original_ios_kexts_prelinked=True,
    iorpc_abi_bytes=24, real_driverkit_iig_implementations=17)
pins['prelink_verification']='build/ios16-prelink/independent-audit.json'
pins['native_candidate']['notes']='30 original executable kexts and codeless IOHIDEventDriver metadata included; no OS root, native HID worker or A660 Metal; no device validation'
for name,scope in [
    ('Nyktis--iig-port','Actual generator used with pinned UniXNU Darwin-target patch and local XNU8796 24-byte IORPC content adapter; 17 target implementations compiled and linked'),
    ('Allenwdk--xnu-linux-toolchain','Reviewed only; simplified/stub RPC path was not selected')]:
    receipt=read(DEV/'research/github-20261103'/(name+'-receipt.json'))
    record={'repository':receipt['repo'],'commit':receipt['commit'],'archive_sha256':receipt['sha256'],
            'scope':scope,'included_in_native_kernel':False}
    pins['github_review_sources']=[p for p in pins['github_review_sources'] if p['repository']!=receipt['repo']]+[record]
write(DEV/'source-pins.json',pins)

report='''# u03：原始 iOS16.5 驱动预链接

已生成约 66 MiB 的 RAM 临时启动候选。没有手机命令、分区写入或设备验收。

## 本轮解决的具体缺口

u02 原生内核的 DriverKit 构建借用了旧 bootstrap shim：16 个实现为空，OSObject 文件集中提供直接转发和不支持的 RPC 占位函数。因此，即使内核没有外部未定义符号，也不代表原始 Apple 驱动所需的 RPC 导出齐全。严格 prelink 首先报缺少 IOService::Start_Invoke。

本轮从 GitHub 固定下载 Nyktis/iig-port @ ea6d147d668ca15d490da638012243fcd705f30d，应用所选 UniXNU 的 Darwin target 补丁，编译实际生成器；根据 XNU8796 原始 IORPC.h，恢复 24 字节的按值 ABI。现代生成器缓存的 kernelContent 访问改为 IORPCMessageFromMach，从实际消息取内容。保留 SDK256 的类声明，17 个生成实现逐个编译并重新链接；旧 RPC 占位源码已被替换。原有增加 kernelContent 字段的补丁已从活动 series 移除。

## 原始驱动输入和解析修正

从 Apple 的 iPhone10,3/iPhone10,6 iOS16.5 / 20F66 IPSW 按范围提取 kernelcache.release.iphone10b，检查 HTTP 范围、长度和 ZIP CRC，解出 arm64 slice 后 SHA256 与固定 profile 相符。

参考项目的正则元数据提取会误读嵌套 XML 和 IDREF。改用 XnuPrelink 的真实 XML 解析后，确认 IOHIDEventDriver 是 codeless 配置插件，依赖 IOHIDFamily；它并非缺失。本轮已将该条目加入 roots，未复制 iPadOS17 地址或 vtable。

## 已执行的检查

- 17 个真实 IIG 实现均为 arm64 iOS16.5 目标编译，带 sizeof(IORPC)==24、sendSize/ replySize 偏移断言，重新链接成功。
- 严格预链接成功：30 个可执行原始驱动及其依赖，另含 IOHIDEventDriver 配置条目。未使用 allow-missing 或 panic/stub 替代未知引用。
- 独立读取最终候选，核对 65,319 个实际指针值、30 个原始驱动 TEXT_EXEC 字节及模块加载地址。
- 64 MiB FAT16 内四文件回读一致；Android v3 镜像各段及保留的 141 个亮屏基线 FFS 完整字节检查通过。
- 生成器仓库的完整 fixture 套件未通过：其新版本行为样例在 XNU8796 头文件下缺少 IIG_CONCRETE 等定义。本轮通过的是上述实际 17 个目标实现的编译、链接和产物检查，不声称完整 fixture 回归通过。

## 当前边界

u03 没有 OS root，不能进入完整 iOS 桌面。原始驱动的结构/指针检查通过不代表 ABI 或启动兼容性已经实测；原生 IOHIDDevice、ST 总线/采集 worker、A660 Metal 尚未接入，crypto 运行时自检尚未执行。旧 HakiOS 的触摸和 GPU 结果不能算作 UniXNU 验收。

下一步是完整系统 RAM root 接入及原生 HID 服务适配；先测量 iOS16.5 的 IOHIDDevice 类布局和入口，再绑定现有 ST 采集参数。仅考虑 RAM 临时启动，不写分区。

## 复现与证据

源码 pin、原始输入 receipt、17 个生成实现与编译记录、旧 shim 备份及内核链接日志均保存在本地。发布目录的 evidence/index.json 提供全部交付证据的 SHA256。

主要脚本：fetch_ios16_kernelcache.py、build_native_iig.py、install_native_iig.py、prepare_ios16_prelink.py、audit_ios16_prelink.py。生成固件/ADT/FAT/boot 的流程沿用已校验的入口，u03 使用 build/prelinked-payload，u01/u02 保持归档。
'''
(DEV/'build/ios16-prelink/PROGRESS.md').write_text(report,encoding='utf-8')
(RELEASE/'u03-progress.md').write_text(report,encoding='utf-8')

readme=(DEV/'README.md').read_text(encoding='utf-8')
readme=readme.replace('MIX4-UniXNU-core-u02','MIX4-UniXNU-core-u03').replace('core-u02-boot.img','core-u03-boot.img')
readme=readme.replace('约 34 MiB','约 66 MiB')
readme=readme.replace('不含原始 Apple kext prelink 和 iOS 根文件系统，不能进入 iOS 桌面；',
    '已预链接 30 个原始 Apple 可执行驱动和 IOHIDEventDriver 配置条目；不含 iOS 根文件系统，不能进入 iOS 桌面；')
readme=readme.replace('补齐原始 kext prelink 和独立 OS root。','补齐独立 OS root 并验证原始驱动启动。')
readme=readme.replace('`scripts/package_core_image.py --release u02`','`scripts/package_core_image.py --release u03 --payload-dir work/UniXNU-odin/build/prelinked-payload`')
readme+='\n## u03 原始驱动预链接\n\n修正 bootstrap IIG 缺失的 RPC 实现，17 个真实实现重新编译链接，恢复原始 24 字节 IORPC ABI。严格 prelink 和 65,319 个指针的独立回读通过，30 个原始驱动代码保持完整字节一致。过程和未通过的 fixture 检查见 `build/ios16-prelink/PROGRESS.md`；实体启动和原生触摸尚未验证。\n'
(DEV/'README.md').write_text(readme,encoding='utf-8')

porting=(DEV/'porting.toml').read_text(encoding='utf-8')
porting=re.sub(r'^summary = .*$', 'summary = "u03 prelinked native kernel with 30 original executable kexts; RAM-boot candidate built; OS root and native HID pending; no UniXNU device test."',porting,count=1,flags=re.M)
updates={
 'configuration': 'Resolved pinned iOS16.5/SM8350 inputs and built u03; version-bound HID ABI is still unqualified.',
 'firmware': 'Native UniXNU/DarwinBoot/SEC assembled; 141 baseline FFS byte-identical; device handoff pending.',
 'cpu': 'Single CPU affinity0 and measured GIC resources staged; no device CPU/GIC qualification.',
 'memory': 'Saved live FDT establishes high DRAM subset and 512 MiB owned-memory request; allocation is not device verified.',
 'storage': 'Original storage-family kexts structurally prelinked; no OS root or persistent partition writes.',
 'input': 'Original IOHIDFamily and codeless IOHIDEventDriver structurally prelinked; no native IOHIDDevice/ST worker linkage.',
 'packaging': 'u03 boot v3 candidate produced with 64 MiB FAT; strict prelink adds 30 executable kexts and HID plugin metadata; not a complete OS.',
 'diagnostics': '17 real IIG implementations compile/link; original IORPC24 ABI asserted; 65319 pointers and 30 executable ranges independently checked; no device commands.'}
blocks=porting.split('[[area]]')
for index in range(1,len(blocks)):
    area=re.search(r'^id = "([^"]+)"',blocks[index],re.M).group(1)
    if area in updates:
        blocks[index]=re.sub(r'^findings = .*$', 'findings = '+json.dumps([updates[area]]),blocks[index],count=1,flags=re.M)
    if area=='packaging':
        blocks[index]=re.sub(r'^paths = .*$', 'paths = ["scripts/**", "patches/xnu/**", "build/ios16-prelink/**"]',blocks[index],count=1,flags=re.M)
porting='[[area]]'.join(blocks)
tomllib.loads(porting)
(DEV/'porting.toml').write_text(porting,encoding='utf-8')

e=RELEASE/'evidence';e.mkdir(exist_ok=True)
paths=[
 'build/ios16-prelink/independent-audit.json',
 'build/ios16-prelink/original-kernel-verification.json',
 'build/ios16-prelink/kernelcache.release.verified.json',
 'build/ios16-prelink/prelink-attempt.json',
 'build/ios16-prelink/u02-native-prelink-attempt.json',
 'build/ios16-prelink/native-iig-evidence-20261103.tar.gz',
 'build/prelinked-payload/kernel-audit.json','build/prelinked-payload/fat-verification.json',
 'build/prelinked-payload/hardware-evidence.json',
 'build/boot-abi/verification.json','build/firmware/verification.json',
 'migration-status.json','source-pins.json']
for path in paths:
    shutil.copyfile(DEV/path,e/path.replace('/','--'))
with tarfile.open(e/'prelink-emission-report.tar.gz','w:gz') as t:
    t.add(BUILD/'prelink-emission-report.json',arcname='prelink-emission-report.json')
write(e/'index.json',{'image_sha256':m['sha256'],
    'files':{p.name:sha(p) for p in sorted(e.iterdir()) if p.is_file() and p.name!='index.json'},
    'device_tested':False,'abi_qualified':False})
print(json.dumps({'image':m['artifact'],'sha256':m['sha256'],'bytes':m['bytes'],
                  'kexts':30,'real_iig_implementations':17,'device_tested':False},indent=2))
