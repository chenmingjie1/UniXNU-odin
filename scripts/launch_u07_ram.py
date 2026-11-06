"""One user-authorized odin u07 RAM boot with durable command evidence.

No flash/erase/set_active/OEM commands. Any command error or timeout stops.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
import os
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[3]
RELEASE=ROOT/'outputs/MIX4-UniXNU-core-u07'
TOOLS=ROOT/'outputs/MIX4-iOS16.5-system-r16-source-kernel/tools'
SERIAL='9bd99408'
NOW=lambda:datetime.now(timezone(timedelta(hours=8))).isoformat()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode',choices=['preflight','boot'])
parser.add_argument('--run-dir',type=Path)
args=parser.parse_args()
if args.run_dir:
    RUN=args.run_dir.resolve()
    assert RUN.is_relative_to((RELEASE/'runs').resolve()) and RUN.is_dir()
else:
    assert args.mode=='preflight'
    RUN=RELEASE/'runs'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    RUN.mkdir(parents=True,exist_ok=False)
env=os.environ.copy();env['ANDROID_USER_HOME']=str(ROOT/'work/adb-user')
events=json.loads((RUN/'events.json').read_text(encoding='utf-8')) if (RUN/'events.json').exists() else []


def record(**data):
    events.append({'at':NOW(),**data})
    (RUN/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def command(tool,tail,timeout=15):
    if tool=='adb':
        assert tail==['devices'] or (tail[:2]==['-s',SERIAL] and
               ((len(tail)==4 and tail[2]=='shell') or tail[2:]==['reboot','bootloader']))
    else:
        assert tail==['devices'] or (tail[:2]==['-s',SERIAL] and
               (tail[2:3]==['getvar'] or tail[2:]==['boot',str(IMAGE)]))
    try:
        p=subprocess.run([str(TOOLS/(tool+'.exe')),*tail],env=env,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as error:
        record(tool=tool,args=tail,error='timeout; no retry or reboot',
               stdout=(error.stdout or b'').decode('utf-8','replace'),
               stderr=(error.stderr or b'').decode('utf-8','replace'))
        raise
    output=(p.stdout+b'\n'+p.stderr).decode('utf-8','replace').strip()
    record(tool=tool,args=tail,returncode=p.returncode,output=output)
    assert p.returncode==0,output
    return output


def shell(text,timeout=15):return command('adb',['-s',SERIAL,'shell',text],timeout)


manifest=json.loads((RELEASE/'manifest.json').read_text(encoding='utf-8'))
IMAGE=(RELEASE/manifest['artifact']).resolve()
assert IMAGE.stat().st_size==manifest['bytes']
assert hashlib.sha256(IMAGE.read_bytes()).hexdigest()==manifest['sha256']=='243be45b5b971cce8edef129c845f09de7d4a83177e2c5fd47346fc7956f35c6'
try:
    if args.mode=='preflight':
        record(event='user_authorized_ram_test',user_message='上机啊',image_sha256=manifest['sha256'])
        assert re.search(r'^'+SERIAL+r'\s+device$',command('adb',['devices']),re.M)
        for prop,value in [('ro.product.device','odin'),('ro.boot.slot_suffix','_b'),('sys.boot_completed','1')]:
            assert shell('getprop '+prop)==value,prop
        assert shell('su -c id').startswith('uid=0')
        battery=shell('dumpsys battery')
        level=re.search(r'^\s*level:\s*(\d+)',battery,re.M)
        assert level and int(level[1])>=40,'Battery must be >=40%'
        boot_id=shell('cat /proc/sys/kernel/random/boot_id')
        baseline=json.loads((ROOT/'outputs/MIX4-iOS16.5-system-r16-source-kernel/manifest.json').read_text(encoding='utf-8'))['partition_baseline']
        for item in baseline['partitions']:
            assert re.fullmatch(r'[a-z0-9_]+',item['name'])
            output=shell("su -c 'sha256sum /dev/block/by-name/"+item['name']+"'",60)
            assert output.split()[0]==item['sha256'],'Partition changed: '+item['name']
            print('verified',item['name'],flush=True)
        evidence={'passed':True,'at':NOW(),'boot_id':boot_id,'image_sha256':manifest['sha256'],
                  'partition_hashes_verified':len(baseline['partitions']),'battery_percent':int(level[1]),
                  'device':'odin','serial':SERIAL,'partition_writes':False}
        (RUN/'preflight.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        record(event='preflight_passed',**evidence)
    else:
        pre=json.loads((RUN/'preflight.json').read_text(encoding='utf-8'))
        assert pre['passed'] and pre['image_sha256']==manifest['sha256']
        assert (datetime.now(timezone(timedelta(hours=8)))-datetime.fromisoformat(pre['at'])).total_seconds()<600
        assert not any(e.get('event')=='ram_boot_attempt' for e in events),'Only one attempt per run'
        assert shell('cat /proc/sys/kernel/random/boot_id')==pre['boot_id'],'Device rebooted after preflight'
        command('adb',['-s',SERIAL,'reboot','bootloader'])
        deadline=time.monotonic()+40
        while True:
            if re.search(r'^'+SERIAL+r'\s+fastboot$',command('fastboot',['devices']),re.M):break
            assert time.monotonic()<deadline,'Fastboot did not enumerate; stop'
            time.sleep(1)
        for key,value in [('product','odin'),('current-slot','b'),('unlocked','yes')]:
            output=command('fastboot',['-s',SERIAL,'getvar',key])
            assert re.search(r'^'+re.escape(key)+r':\s*'+value+r'\s*$',output,re.M),output
        record(event='ram_boot_attempt',image_sha256=manifest['sha256'],partition_writes=False)
        output=command('fastboot',['-s',SERIAL,'boot',str(IMAGE)],45)
        assert 'OKAY' in output
        record(event='bootloader_accepted_ram_boot',kernel_execution_confirmed=False,
               physical_screen_confirmed=False,partition_writes=False)
        print(output,flush=True)
except Exception as error:
    record(event='stopped',error=repr(error),automatic_retry=False,automatic_reboot=False)
    raise
finally:
    print('Evidence:',RUN,flush=True)
