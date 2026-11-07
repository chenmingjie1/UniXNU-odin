"""Verify and serve the fixed MIX 4 u88 desktop runtime with Android fastboot."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

MAX_RESPONSE = 0x100000

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def resolve_file(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('Invalid runtime relative path')
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('Runtime path escapes package directory')
    return path

def verify(root):
    manifest = json.loads((root / 'runtime-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('release') != 'u88' or manifest.get('device') != 'odin':
        raise ValueError('This launcher only supports the fixed u88 / odin runtime')
    if manifest.get('remote_serial') != 'odin-unixnu-u64' or not manifest.get('resident_core7'):
        raise ValueError('Unexpected firmware transport')
    seen_ids, seen_names, files = set(), set(), {}
    for entry in manifest['files']:
        if entry['id'] in seen_ids or entry['uefi_path'] in seen_names:
            raise ValueError('Duplicate runtime file ID or firmware path')
        seen_ids.add(entry['id']); seen_names.add(entry['uefi_path'])
        if entry['path'] is None:
            continue
        path = resolve_file(root, entry['path'])
        if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError('Runtime file does not match u88: ' + entry['path'])
        files[entry['id']] = dict(entry, absolute=path, mtime=path.stat().st_mtime_ns)
        print('Verified:', entry['path'], flush=True)
    if set(files) != set(range(4,11)):
        raise ValueError('u88 firmware requires all seven exact files (IDs 4..10)')
    boot = resolve_file(root, manifest['boot']['path'])
    if boot.stat().st_size != manifest['boot']['bytes'] or sha(boot) != manifest['boot']['sha256']:
        raise ValueError('Boot image does not match u88')
    return manifest, files, boot

def response(files, fileid, offset, wanted, sequence):
    if fileid not in files or not 0 < wanted <= MAX_RESPONSE:
        raise ValueError('Firmware requested an unknown file or invalid length')
    item = files[fileid]
    if offset < 0 or offset > item['bytes'] or wanted > item['bytes'] - offset:
        raise ValueError('Firmware read outside the pinned file')
    stat = item['absolute'].stat()
    if stat.st_size != item['bytes'] or stat.st_mtime_ns != item['mtime']:
        raise ValueError('Pinned file changed while serving')
    with item['absolute'].open('rb') as stream:
        stream.seek(offset); data = stream.read(wanted)
    if len(data) != wanted:
        raise ValueError('Short runtime file read')
    return struct.pack('<8sIIQII', b'ODNRD001', sequence, fileid, offset, wanted, zlib.crc32(data) & 0xffffffff) + data

class Fastboot:
    def __init__(self, executable):
        self.executable = executable
    def run(self, *args, timeout=20, required=True):
        process = subprocess.run([self.executable, *map(str,args)], capture_output=True, timeout=timeout)
        output = (process.stdout+b'\n'+process.stderr).decode('utf-8',errors='replace').strip()
        if required and process.returncode:
            raise RuntimeError('fastboot failed: ' + output)
        return process.returncode, output
    def devices(self):
        _, output = self.run('devices')
        return [m[0] for m in re.findall(r'^(\S+)\s+(fastboot)\b', output, re.M)]

def ram_boot(fastboot, serial, image):
    if serial not in fastboot.devices():
        raise RuntimeError('Selected device is not in fastboot mode; use adb reboot bootloader first')
    for key, value in (('product','odin'),('unlocked','yes')):
        _, output = fastboot.run('-s',serial,'getvar',key)
        if not re.search(r'\b'+key+r':\s*'+value+r'\b',output):
            raise RuntimeError('Device check failed ('+key+'): '+output)
    fastboot.run('-s',serial,'boot',image,timeout=60)
    print('MIX 4 accepted the temporary u88 boot image. Waiting for USB media requests.',flush=True)

def serve(fastboot, manifest, files, root, seconds, log):
    remote = manifest['remote_serial']
    start = time.monotonic(); last_active = start; total = 0; last_id = None; last_sequence = None; last_progress = 0
    chunk = log.parent / 'current-response.bin'
    def record(**entry):
        with log.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**entry})+'\n')
    while time.monotonic() - start < seconds:
        devices = fastboot.devices()
        if remote not in devices:
            if time.monotonic() - last_active > 120:
                raise RuntimeError('Runtime USB device missing for 120 seconds; see events.jsonl and screen diagnostics')
            time.sleep(.3);continue
        _, query = fastboot.run('-s',remote,'getvar','odin-read')
        if 'idle:desktop-ready' in query:
            fastboot.run('-s',remote,'oem','desktop');last_active=time.monotonic()
            record(event='desktop_start_requested');continue
        if 'idle:uefi-stopped' in query:
            _, status = fastboot.run('-s',remote,'getvar','result',required=False)
            record(event='uefi_stopped',status=status,bytes_served=total)
            raise RuntimeError('Firmware loader returned: '+status)
        if 'idle:kernel-core7' in query:
            record(event='kernel_core7',bytes_served=total)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                _, stage=fastboot.run('-s',remote,'getvar','kernel-postvm',required=False)
                match=re.search(r'stage=([0-9a-fA-F]+)',stage)
                if match and int(match[1],16)>=0x4e:
                    _, policy=fastboot.run('-s',remote,'oem','ui-wake')
                    record(event='ui_idle_assertion_requested',postvm=stage,reply=policy)
                    print('Media served. Kernel reached post-VM; requested the u88 UI idle assertion.',flush=True)
                    for key in ('kernel-panic','kernel-stage','kernel-postvm'):
                        _, info=fastboot.run('-s',remote,'getvar',key,required=False)
                        record(event='diagnostic',key=key,reply=info)
                    print('Check the phone for SpringBoard. This message does not itself confirm a desktop.',flush=True)
                    return
                time.sleep(.25)
            record(event='postvm_timeout',last_reply=stage)
            raise RuntimeError('Kernel post-VM stage not reached; attach events.jsonl and a screen photo')
        match=re.search(r'odin-read:\s*([0-9a-fA-F]{8}):([0-9a-fA-F]{8}):([0-9a-fA-F]{16}):([0-9a-fA-F]{8})',query)
        if not match:raise RuntimeError('Unknown u88 USB response: '+query)
        seq,fileid,offset,wanted=[int(x,16) for x in match.groups()]
        if seq==last_sequence:raise RuntimeError('Repeated completed read request; refusing stale response')
        chunk.write_bytes(response(files,fileid,offset,wanted,seq))
        fastboot.run('-s',remote,'stage',chunk,timeout=60)
        total+=wanted;last_active=time.monotonic();last_sequence=seq
        record(event='read',file=fileid,sequence=seq,offset=offset,bytes=wanted,total=total)
        if fileid!=last_id or total-last_progress >= 128*1024*1024:
            print('Serving:',files[fileid]['path'],'total MiB',round(total/1048576,1),flush=True)
            last_progress=total;last_id=fileid
    raise RuntimeError('Serving time limit reached before the kernel handoff')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--verify-only',action='store_true',help='Check all files without accessing a device')
    parser.add_argument('--boot',action='store_true',help='Temporary fastboot boot, then serve the pinned runtime')
    parser.add_argument('--serial',help='Your own Android fastboot serial; required with --boot')
    parser.add_argument('--fastboot',default='fastboot',help='Android SDK platform-tools fastboot executable')
    parser.add_argument('--seconds',type=int,default=1800)
    args=parser.parse_args()
    if args.boot and not args.serial:parser.error('--serial is required with --boot')
    if not 120<=args.seconds<=7200:parser.error('--seconds must be 120..7200')
    manifest,files,image=verify(args.runtime.resolve())
    if args.verify_only:
        print('All u88 runtime files match. No device commands executed.');return
    executable=shutil.which(args.fastboot)
    if not executable:parser.error('Install Android SDK platform-tools and put fastboot on PATH, or use --fastboot')
    fastboot=Fastboot(executable)
    run=args.runtime.resolve()/'runs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    run.mkdir(parents=True,exist_ok=False)
    print('Log directory:',run,flush=True)
    if args.boot:ram_boot(fastboot,args.serial,image)
    serve(fastboot,manifest,files,args.runtime.resolve(),args.seconds,run/'events.jsonl')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        print('STOP:',error,file=sys.stderr);sys.exit(1)
