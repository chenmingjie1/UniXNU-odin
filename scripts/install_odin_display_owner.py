"""VM-only opt-in display hook; never touches a physical device."""
from pathlib import Path
import argparse,hashlib,json

root=Path('/home/odin/unixnu-odin-build')
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',default='u16')
a=p.parse_args();assert a.tag.isalnum()
out=root/('evidence/odin-display-owner-'+a.tag)
source=root/'upstream/.cache/xnu-work/bsd/kern/kern_exec.c'
backup=out/'kern_exec.before-display.c'
before=source.read_bytes()
marker='/* ODIN_DISPLAY_OWNER_U15: computer replay only, disabled by default. */'
text=before.decode()
if marker not in text:
    assert not backup.exists(), 'Refuse to overwrite source backup'
    backup.write_bytes(before)
    anchor='#if CONFIG_MEMORYSTATUS\n\t(void) memorystatus_init_at_boot_snapshot();'
    assert text.count(anchor)==1
    hook='''#if defined(XNU_ODIN_DISPLAY_OWNER) && XNU_ODIN_DISPLAY_OWNER
	/* ODIN_DISPLAY_OWNER_U15: computer replay only, disabled by default. */
	extern void odin_display_owner_start(void);
	odin_display_owner_start();
#endif
'''
    source.write_text(text.replace(anchor,hook+anchor))
elif not backup.exists():
    backup.write_bytes(before)
link=(root/'link_offline_kernel.sh').read_text()
assert 'XNU_ODIN_DISPLAY_OWNER' not in link
link=link.replace('archives="-L','archives="-Wl,-force_load,'+str(out/'libOdinDisplay.a')+' -L',1)
needle='kern_exec.o_CFLAGS_ADD=\'-DXNU_OWNER_DATA_MOUNT=1 '
assert link.count(needle)==1
link=link.replace(needle,"kern_exec.o_CFLAGS_ADD='-DXNU_ODIN_DISPLAY_OWNER=1 -DXNU_OWNER_DATA_MOUNT=1 ")
link=link.replace('evidence/kernel-final.log','evidence/odin-display-owner-'+a.tag+'/kernel-link.log')
link=link.replace('evidence/kernel-crypto-seal.log','evidence/odin-display-owner-'+a.tag+'/kernel-crypto-seal.log')
# XNU make does not track changes in LD_KERNEL_ARCHIVES. Invalidate its
# derived link target explicitly; preserve the preceding kernel first.
relink='''python3 - <<'PY'
from pathlib import Path
import shutil
p=Path('/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped')
b=Path('''+repr(str(out/'kernel-before-relink.macho'))+''')
if p.exists():
    if not b.exists():shutil.copy2(p,b)
    p.unlink()
PY
'''
assert link.count('bash build_offline_kernel.sh')==1
link=link.replace('bash build_offline_kernel.sh',relink+'bash build_offline_kernel.sh')
(out/'link_display_kernel.sh').write_text(link)
(out/'integration-receipt.json').write_text(json.dumps(dict(
    source_before_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
    source_after_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    default_disabled=True,device_commands_executed=False),indent=2)+'\n')
print('Installed gated computer-only display lifecycle hook; backup preserved')
