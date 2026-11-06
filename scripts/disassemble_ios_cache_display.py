"""Bounded read-only disassembly of the exact iOS16 user display library."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--address',required=True,type=lambda v:int(v,0))
p.add_argument('--bytes',default=512,type=lambda v:int(v,0))
p.add_argument('--output',required=True)
a=p.parse_args();assert 4<=a.bytes<=16384 and a.bytes%4==0
out=ROOT/'work/UniXNU-odin/build/display-owner-u15'/a.output
assert out.resolve().parent==(ROOT/'work/UniXNU-odin/build/display-owner-u15').resolve()
c=Cache(DEFAULT);where=c.resolve(a.address)
blob=c.read(a.address,a.bytes);c.close()
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
    '-o','UserKnownHostsFile='+str(ROOT/'outputs/MIX4-odin-porting/kernel-touch-init-integrated-20261101/guest-known-hosts'),
    '-i',str(ROOT/'work/odin-portable-linux/guest-ssh-key'),'-p','18474','odin@127.0.0.1',
    'llvm-mc --disassemble --triple=aarch64']
r=subprocess.run(ssh,input=' '.join(hex(v) for v in blob)+'\n',capture_output=True,text=True,check=True,timeout=30)
assert not r.stderr,r.stderr
lines=[s.strip() for s in r.stdout.splitlines() if s.strip() and s.strip()!='.text']
assert len(lines)==a.bytes//4
text=json.dumps(where)+'\n'+'\n'.join(f'{a.address+i*4:#x}: {line}' for i,line in enumerate(lines))+'\n'
out.write_text(text);print(text)
