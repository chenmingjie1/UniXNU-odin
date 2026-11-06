"""Serve only the seven pinned desktop files to the phone's read-only UEFI FS.

--boot performs the authorized RAM boot first. No flash, erase, format,
partition write, slot switch, or arbitrary host file path is implemented.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,struct,subprocess,time,zlib
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
REL=ROOT/'outputs/MIX4-UniXNU-desktop-u64'
TOOLS=ROOT/'outputs/MIX4-iOS16.5-touch-userland-r64-input-sampler/tools'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--boot',action='store_true');p.add_argument('--seconds',type=int,default=1800);p.add_argument('--release',choices=['u64','u65','u66','u67','u68','u69','u70','u71','u72','u73','u74','u75','u76','u77','u78','u79','u80','u81','u82','u83','u84','u85','u86','u87','u88','u89','u90','u91'],default='u64');p.add_argument('--wait-android',type=int,default=0,help='Wait this many seconds for the paired Android device before the authorized RAM boot');p.add_argument('--arm-ui-idle-assertion',action='store_true',help='u88/u89 fixture: request original UI idle assertion after post-VM entry, before automatic UI lock');args=p.parse_args()
assert not args.arm_ui_idle_assertion or args.release in ('u88','u89','u90','u91')
assert 0<=args.wait_android<=1800
assert not args.wait_android or args.boot,'--wait-android requires --boot'
if args.release!='u64':REL=ROOT/('outputs/MIX4-UniXNU-desktop-'+args.release)
manifest=json.loads((REL/'manifest.json').read_text())
serial=manifest['serial'];remote=manifest['remote_serial'];image=REL/manifest['artifact']
RUN=REL/'runs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S');RUN.mkdir(parents=True,exist_ok=False)
events=[];records=[]
def record(**data):
 data={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**data};events.append(data)
 with (RUN/'events.jsonl').open('a') as f:f.write(json.dumps(data)+'\n')
def cmd(tool,tail,timeout=15,allow_failure=False):
 r=subprocess.run([str(TOOLS/(tool+'.exe')),*tail],capture_output=True,timeout=timeout)
 output=(r.stdout+b'\n'+r.stderr).decode(errors='replace').strip()
 if not allow_failure:assert r.returncode==0,output
 return r.returncode,output
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
assert sha(image)==manifest['sha256']
media=json.loads(Path(manifest['source_media_manifest']).read_text())
media_root=Path(manifest.get('media_root',str(DEV/'build/device-desktop-u63'))).resolve()
assert media_root.is_relative_to((DEV/'build').resolve())
expected={str((media_root/x['path']).resolve()):x['sha256'] for x in media['files']}
filemap={}
for entry in manifest['remote_files']:
 if entry['path'] is None:continue
 path=Path(entry['path']).resolve();assert path.is_relative_to((media_root/'esp').resolve())
 assert path.stat().st_size==entry['bytes']
 digest=sha(path)
 if str(path) in expected:assert digest==expected[str(path)],str(path)
 filemap[entry['id']]={'path':path,'bytes':entry['bytes'],'sha256':digest,'mtime':path.stat().st_mtime_ns,'file':path.open('rb')}
record(event='inputs_verified',image_sha256=manifest['sha256'],files={k:{a:str(b) if isinstance(b,Path) else b for a,b in v.items() if a!='file'} for k,v in filemap.items()})
if args.boot:
 deadline=time.monotonic()+args.wait_android
 if args.wait_android:
  print('Waiting up to',args.wait_android,'seconds for Android recovery; RAM boot will start automatically',flush=True)
  record(event='waiting_for_android',maximum_seconds=args.wait_android)
 while True:
  _,devices=cmd('adb',['devices','-l'])
  if re.search(r'^'+serial+r'\s+device\b',devices,re.M):
   _,completed=cmd('adb',['-s',serial,'shell','getprop sys.boot_completed'],allow_failure=True)
   if completed=='1':break
  if time.monotonic()>=deadline:
   record(event='android_unavailable',devices=devices)
   raise RuntimeError('Paired Android device unavailable; no RAM boot or partition writes performed')
  time.sleep(1)
 for prop,value in [('ro.product.device','odin'),('sys.boot_completed','1')]:
  _,output=cmd('adb',['-s',serial,'shell','getprop '+prop]);assert output==value,(prop,output)
 _,battery=cmd('adb',['-s',serial,'shell','dumpsys battery'])
 level=re.search(r'^\s*level:\s*(\d+)',battery,re.M)
 present=re.search(r'^\s*present:\s*true\b',battery,re.M)
 battery_source='Android BatteryService'
 if not present or not level:
  # Some modified Android ROMs report an absent battery through BatteryService.
  # Read the paired phone's actual kernel battery driver; never invent a level.
  _,hardware=cmd('adb',['-s',serial,'shell',"su -c 'cat /sys/class/power_supply/battery/uevent'"])
  values=dict(line.strip().split('=',1) for line in hardware.splitlines() if line.startswith('POWER_SUPPLY_') and '=' in line)
  assert values.get('POWER_SUPPLY_PRESENT')=='1' and values.get('POWER_SUPPLY_HEALTH')=='Good',hardware
  measured=values.get('POWER_SUPPLY_CAPACITY','')
  assert measured.isdecimal() and 30<=int(measured)<=100,hardware
  record(event='battery_service_inconsistent',service=battery,kernel_uevent=hardware)
  percent=int(measured);battery_source='kernel power_supply/battery/uevent'
 else:
  percent=int(level[1]);assert 30<=percent<=100,battery
 record(event='android_preflight',battery=percent,battery_source=battery_source,device='odin')
 _,output=cmd('adb',['-s',serial,'reboot','bootloader']);record(event='reboot_bootloader',output=output)
 end=time.monotonic()+45
 while time.monotonic()<end:
  _,devices=cmd('fastboot',['devices'])
  if re.search(r'^'+serial+r'\s+fastboot',devices,re.M):break
  time.sleep(1)
 else:raise RuntimeError('Phone bootloader did not enumerate')
 for key,value in [('product','odin'),('unlocked','yes')]:
  _,output=cmd('fastboot',['-s',serial,'getvar',key]);assert re.search(r'\b'+key+r':\s*'+value+r'\b',output),output
 record(event='ram_boot_attempt',image_sha256=manifest['sha256'],partition_writes=False)
 _,output=cmd('fastboot',['-s',serial,'boot',str(image)],45);record(event='ram_boot_accepted',output=output)
 print('Phone accepted '+args.release+' RAM boot; waiting for read-only USB media',flush=True)
end=time.monotonic()+args.seconds;last_sequence=None;total=0;last_progress=0;waiting=time.monotonic();last_id=None
chunk=RUN/'current-response.bin'
try:
 while time.monotonic()<end:
  _,devices=cmd('fastboot',['devices'])
  if not re.search(r'^'+remote+r'\s+fastboot',devices,re.M):
   if time.monotonic()-waiting>120:
    record(event='usb_not_enumerated',bytes_served=total);break
   time.sleep(.5);continue
  try:
   code,output=cmd('fastboot',['-s',remote,'getvar','odin-read'],20,True)
  except subprocess.TimeoutExpired:
   record(event='read_query_timeout_after_handoff',bytes_served=total);break
  if code:
   record(event='read_query_failed',output=output,bytes_served=total);break
  if 'idle:desktop-ready' in output:
   _,output=cmd('fastboot',['-s',remote,'oem','desktop'],20)
   record(event='desktop_start_requested',output=output);waiting=time.monotonic();continue
  if 'idle:uefi-stopped' in output:
   _,status=cmd('fastboot',['-s',remote,'getvar','result'],20)
   record(event='uefi_boot_returned',status=status,bytes_served=total)
   print('UEFI boot stopped:',status,flush=True)
   _,recovery=cmd('fastboot',['-s',remote,'reboot'],20)
   record(event='android_recovery_requested',output=recovery)
   break
  if 'idle:kernel-core7' in output:
   _,status=cmd('fastboot',['-s',remote,'getvar','result'],20)
   record(event='resident_core7_control_available',status=status,bytes_served=total)
   print('Resident firmware retained USB control:',status,flush=True)
   if args.arm_ui_idle_assertion:
    # The assertion prevents future idle lock; it cannot unlock a UI that has
    # already slept. Arm the fixed RAM command before the helper's first poll.
    # Wait for post-VM so the kernel's zero-fill initialization is complete.
    deadline=time.monotonic()+60
    while True:
     _,postvm=cmd('fastboot',['-s',remote,'getvar','kernel-postvm'],10,True)
     match=re.search(r'stage=([0-9a-fA-F]+)',postvm)
     if match and int(match[1],16)>=0x4e:break
     assert time.monotonic()<deadline,'Post-VM entry not observed; UI policy not armed'
     time.sleep(.25)
    _,policy=cmd('fastboot',['-s',remote,'oem','ui-wake'],10)
    record(event='ui_idle_assertion_armed_before_helper',postvm=postvm,output=policy)
    print('Original UI idle assertion requested before SpringBoard helper startup',flush=True)
   # Leave the desktop running. No reboot and no second kernel launch.
   break
  match=re.search(r'odin-read:\s*([0-9a-fA-F]{8}):([0-9a-fA-F]{8}):([0-9a-fA-F]{16}):([0-9a-fA-F]{8})',output)
  assert match,output
  seq,fileid,offset,wanted=[int(x,16) for x in match.groups()]
  assert seq!=last_sequence,'Repeated completed request; stopping rather than replaying stale bytes'
  assert fileid in filemap and 0<wanted<=0x100000
  info=filemap[fileid];assert offset<=info['bytes'] and wanted<=info['bytes']-offset
  st=info['path'].stat();assert st.st_size==info['bytes'] and st.st_mtime_ns==info['mtime'],'Pinned input changed'
  f=info['file'];f.seek(offset);data=f.read(wanted);assert len(data)==wanted
  header=struct.pack('<8sIIQII',b'ODNRD001',seq,fileid,offset,wanted,zlib.crc32(data)&0xffffffff)
  chunk.write_bytes(header+data)
  _,output=cmd('fastboot',['-s',remote,'stage',str(chunk)],45)
  last_sequence=seq;total+=wanted;waiting=time.monotonic()
  records.append({'sequence':seq,'file':fileid,'offset':offset,'bytes':wanted})
  with (RUN/'reads.jsonl').open('a') as log:log.write(json.dumps(records[-1])+'\n')
  if fileid!=last_id or total-last_progress>=128*1024*1024:
   print('Served',fileid,info['path'].name,'offset',hex(offset),'total MiB',round(total/1048576,1),flush=True)
   record(event='read_progress',file=fileid,offset=offset,total_bytes=total);last_progress=total;last_id=fileid
finally:
 for info in filemap.values():info['file'].close()
 report={'bytes_served':total,'read_requests':len(records),'partition_writes':False,'run':str(RUN),'physical_desktop_confirmed':False}
 (RUN/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
