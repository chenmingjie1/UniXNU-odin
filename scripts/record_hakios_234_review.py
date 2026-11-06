"""Pin a source review and upstream patches; never issue a phone command."""
from pathlib import Path
import datetime, hashlib, json, subprocess

DEV = Path(__file__).resolve().parents[1]
ROOT = DEV.parents[1]
OUT = DEV/'research/hakios-2.3.4-20261106'
SOURCE = OUT/'source'
REV = '2631f5d7d4f9d7322aca60991b34ba465dec343b'
def git(*args):
    return subprocess.run(['git','-C',str(SOURCE),*args],capture_output=True,
                          check=True,encoding='utf-8').stdout
assert git('rev-parse','HEAD').strip() == REV
assert not git('status','--porcelain').strip()
assert 'SUBLEVEL = 4' in (SOURCE/'Makefile').read_text() or '2.3.4' in (SOURCE/'CHANGELOG.md').read_text()
commits = [
    ('81b5dd2','touch-active-poll'),('a3975b6','touch-session-measurement'),
    ('539d35e','framebuffer-settle-surface-lifetime'),('f8976bc','display-interface-soc-guard'),
    ('d18f6bd','metal-chip-guard'),('9da1523','per-device-metal-arguments'),
    ('3b9db78','coreanimation-shader-variants'),('a128588','integrated-metal-history'),
    ('6bd9fee','integrated-metal-build')]
patches = OUT/'patches'
patches.mkdir(exist_ok=True)
records=[]
for short, name in commits:
    full=git('rev-parse',short).strip()
    text=git('show','--format=fuller','--no-ext-diff',full)
    path=patches/(short+'-'+name+'.patch')
    path.write_text(text,encoding='utf-8')
    records.append(dict(commit=full,subject=git('show','-s','--format=%s',full).strip(),
        url='https://github.com/oosexgang/hakios-xnu-kernel/commit/'+full,
        patch=str(path.relative_to(OUT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
anchors={
    'drivers/input/hakios.goodix.c':['focaltech_poll(void)','chip_touching(void)','idle_looks = 16000','|| chip_touching()'],
    'xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp':['#define FAST_FRAMES','panelInterface(void)','shownDrawn[SWAP_LAYERS]','surfaces[layer]->drawn != shownDrawn[layer]'],
    'hakios-metal/src/c_api.cpp':['bool hakios_metal_chip_known'],
    'hakios-metal/include/hakios-metal/a6xx.hpp':['kChipId =','kNumSpCores ='],
    'userland/src/HakiosMetalCA.m':['hm_ca_nearest(NSString *frag)'],
    'tools/metal-run.sh':['devices/$device/metal.args','DEVICE_ARGS="fb_hz=60 fb_threads=3"'],
    'docs/porting/index.md':['## Metal and the panel'],
    'docs/reference/metal-measurements.md':['### Under real fingers'],
    'CHANGELOG.md':['## 2026-11-05: 2.3.4']}
sources=[]
for relative, needles in anchors.items():
    path=SOURCE/relative
    lines=path.read_text(encoding='utf-8').splitlines()
    found={needle:[i for i,line in enumerate(lines,1) if needle in line] for needle in needles}
    assert all(found.values()),(relative,found)
    sources.append(dict(path=relative,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),anchors=found,
        url=f'https://github.com/oosexgang/hakios-xnu-kernel/blob/{REV}/{relative}'))
receipt=dict(repository='https://github.com/oosexgang/hakios-xnu-kernel',revision=REV,
    reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    official_changelog='https://hackios-web.vercel.app/en/changelog',
    scope='2.3.4 announcement and included 2.3.3 fixes; exact source commits reviewed',
    tags_note='No 2.3.4/v2.3.4 tag was advertised by the focused ls-remote; pinned main commit includes 2.3.4 changelog',
    commits=records,sources=sources,phone_commands_executed=False,
    patches_applied_to_unixnu=False,physical_improvement_verified=False)
(OUT/'review.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
status_path=DEV/'migration-status.json'
status=json.loads(status_path.read_text())
status.update(upstream_234_review=str(OUT/'MIX4-2.3.4-review.md'),
    upstream_234_revision=REV,upstream_234_receipt=str(OUT/'review.json'),
    upstream_234_patches_applied=False)
status_path.write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(dict(revision=REV,commits=len(records),source_files=len(sources),
    phone_commands_executed=False,patches_applied_to_unixnu=False),indent=2))
