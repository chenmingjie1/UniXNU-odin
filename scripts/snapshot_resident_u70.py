"""Read fixed native status and GOP pixels; never reboot or write device storage."""
from pathlib import Path
import argparse,datetime,json,re,subprocess,time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wait-run',type=Path,help='Wait boundedly for the matching media-server resident event')
parser.add_argument('--release',choices=['u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91'],default='u70')
options=parser.parse_args()
if options.wait_run:
 deadline=time.monotonic()+600
 while True:
  file=options.wait_run/'events.jsonl'
  events=[json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []
  if any(e['event']=='resident_core7_control_available' for e in events):break
  assert not any(e['event'] in ('uefi_boot_returned','read_query_timeout_after_handoff','usb_not_enumerated') for e in events),'This boot did not reach the resident interface'
  assert time.monotonic()<deadline,'Resident capture wait expired'
  time.sleep(1)
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parents[1]
TOOLS=ROOT/'outputs/MIX4-iOS16.5-touch-userland-r64-input-sampler/tools'
OUT=ROOT/('outputs/MIX4-UniXNU-desktop-'+options.release+'/resident-snapshots')/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
OUT.mkdir(parents=True)
serial='odin-unixnu-u64'
def run(args,timeout=10):
 p=subprocess.run([str(TOOLS/'fastboot.exe'),'-s',serial,*args],capture_output=True,timeout=timeout)
 text=(p.stdout+b'\n'+p.stderr).decode(errors='replace').strip()
 return dict(returncode=p.returncode,text=text)
devices=subprocess.run([str(TOOLS/'fastboot.exe'),'devices'],capture_output=True,timeout=5)
assert re.search(r'^'+serial+r'\s+fastboot',devices.stdout.decode(),re.M),'Resident USB not present; no blocking wait or device writes'
result={}
for name,args in [('resident',['getvar','result']),('stage',['getvar','kernel-stage']),
                  *([('postvm',['getvar','kernel-postvm']),('panic',['oem','kernel-panic'])] if options.release in ('u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91') else []),
                  *([(name,['oem',name+'-stats']) for name in ('touch','hid','gpu',*(['present'] if options.release in ('u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91') else []))] if options.release in ('u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91') else []),
                  *([('surface',['oem','surface-stats'])] if options.release in ('u82','u83','u84','u85','u86','u87','u88','u89','u90','u91') else []),
                  *([('gpu-log',['oem','gpu-log'])] if options.release in ('u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91') else []),*([('ui-threads',['oem','ui-threads'])] if options.release in ('u83','u84','u85','u86','u87','u88','u89','u90','u91') else []),*([('ui-policy',['oem','ui-policy'])] if options.release in ('u85','u86','u87','u88','u89','u90','u91') else []),('log',['oem','kernel-log']),('framebuffer',['getvar','framebuffer'])]:
 result[name]=run(args)
 (OUT/(name+'.txt')).write_text(result[name]['text']+'\n')
 (OUT/'status.json').write_text(json.dumps(result,indent=2)+'\n')
 print(name,result[name]['text'],flush=True)
match=re.search(r'framebuffer:\s*(\d+):(\d+):(\d+):(\d+):(\d+)',result['framebuffer']['text'])
if match:
 width,height,stride,fmt,size=map(int,match.groups())
 assert 0<width<=8192 and 0<height<=8192 and width*4<=stride<=8192*4 and size==stride*height and size<=64*1024**2 and fmt in (0,1)
 raw=OUT/'framebuffer.bin';result['capture']=run(['get_staged',str(raw)],30)
 assert not result['capture']['returncode'] and raw.stat().st_size==size,result['capture']
 from PIL import Image
 pixels=Image.frombytes('RGB',(width,height),raw.read_bytes(),'raw','RGBX' if fmt==0 else 'BGRX',stride,1)
 png=OUT/'framebuffer.png';pixels.save(png)
 result['image']=str(png)
 (OUT/'status.json').write_text(json.dumps(result,indent=2)+'\n')
 print(png,flush=True)
print(OUT,flush=True)
