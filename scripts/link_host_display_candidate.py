"""Link and independently audit a display candidate in the Linux VM. No device I/O."""
from pathlib import Path
import argparse
import subprocess
import sys

from build_odin_display_owner import DEV, ROOT, SSH, SCP

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',required=True)
p.add_argument('--driver-policy',type=Path,required=True)
a=p.parse_args()
assert a.tag.isalnum()
out=DEV/('build/display-owner-'+a.tag)
remote='/home/odin/unixnu-odin-build/evidence/odin-display-owner-'+a.tag
assert (out/'interface-compiler-audit.json').exists()
assert not (out/'native-real-iig.macho').exists(), 'Preserve linked candidates; use another tag'

def run(command,log=None):
    if log:
        with (out/log).open('w',encoding='utf-8') as stream:
            subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    else:
        subprocess.run(command,cwd=ROOT,check=True)

run([*SCP,str(DEV/'scripts/install_odin_display_owner.py'),'odin@127.0.0.1:'+remote+'/'])
run([*SSH,'python3 '+remote+'/install_odin_display_owner.py --tag '+a.tag])
run([*SSH,'bash '+remote+'/link_display_kernel.sh'], 'host-link-console.log')
run([*SCP,'odin@127.0.0.1:/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped',str(out/'native-real-iig.macho')])
run([*SCP,'odin@127.0.0.1:'+remote+'/{integration-receipt.json,link_display_kernel.sh,kernel-link.log,kernel-crypto-seal.log}',str(out)])
run([sys.executable,'-X','utf8',str(DEV/'scripts/prepare_ios16_prelink.py'),
     '--kernel',str(out/'native-real-iig.macho'),'--output-dir',str(out),
     '--driver-policy',str(a.driver_policy.resolve())], 'prelink-console.log')
run([sys.executable,'-X','utf8',str(DEV/'scripts/audit_ios16_prelink.py'),
     '--input-dir',str(out)], 'independent-audit-console.log')
run([sys.executable,'-X','utf8',str(DEV/'scripts/audit_odin_display_link.py'),
     '--tag',a.tag], 'display-link-audit-console.log')
print('PASS: host candidate linked and prelinked; original bytes and display dispatch independently audited')
