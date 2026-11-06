"""Build a finite host-only swipe tool against actual iOS16.5 exports.

Uses minimal linker stubs generated from verified cache exports, no guessed
IOHIDDevice vtable, kernel changes, DYLD injection, or phone commands.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import argparse
import plistlib
import struct
from inspect_cache_objc_refs import Cache, DEFAULT
from build_odin_display_owner import SSH, SCP
from inspect_root_exec import audit_file
from symbolicate_ios_stacks import uleb

DEV = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag', default='u50')
p.add_argument('--event-dispatch-entitlement', action='store_true')
p.add_argument('--unlock-ui', action='store_true', help='Build the separate, finite SBS UI request tool')
p.add_argument('--sb-unlock-library', action='store_true', help='Build the narrow upstream-style SpringBoard UI component')
p.add_argument('--statusbar-library', action='store_true', help='Build the MIX 4 original UIKit status bar provider fix')
p.add_argument('--statusbar-with-unlock', action='store_true', help='Include status bar fix in the existing kernel-selected UI library')
p.add_argument('--idle-policy-with-unlock', action='store_true')
p.add_argument('--idle-policy-disable', action='store_true', help='Use original UIApplication idle-disable API instead of idle reset')
p.add_argument('--idle-policy-system', action='store_true', help='Use original SBBacklightController preventIdleSleep/allowIdleSleep')
p.add_argument('--idle-policy-assertion', action='store_true', help='Acquire and retain original global UI idle-disable assertion')
p.add_argument('--gpu-surface-probe', action='store_true', help='One background original-IOSurface GPU import/write/readback probe')
args = p.parse_args()
assert args.tag.isalnum()
assert sum((args.unlock_ui, args.sb_unlock_library, args.statusbar_library)) <= 1
assert not args.statusbar_with_unlock or args.sb_unlock_library
assert not args.idle_policy_with_unlock or (args.sb_unlock_library and args.statusbar_with_unlock)
assert not args.idle_policy_disable or args.idle_policy_with_unlock
assert not args.idle_policy_system or (args.idle_policy_with_unlock and not args.idle_policy_disable)
assert not args.idle_policy_assertion or (args.idle_policy_with_unlock and not args.idle_policy_disable and not args.idle_policy_system)
assert not args.gpu_surface_probe or (args.idle_policy_assertion and args.sb_unlock_library)
for command in (SSH, SCP):
    command[command.index('-i') + 1] = str(DEV / 'build/touch-metal-u74/guest-ssh-key')
with_entitlement = args.event_dispatch_entitlement
assert not (args.unlock_ui and with_entitlement)
assert not (args.sb_unlock_library and (args.unlock_ui or with_entitlement))
out = DEV / ('build/host-virtual-input-' + args.tag)
out.mkdir(exist_ok=True)
assert not (out / 'host_swipe').exists()
remote = '/home/odin/unixnu-odin-build/evidence/host-virtual-input-' + args.tag
source = DEV / ('host-input/statusbar_1080.c' if args.statusbar_library else 'host-input/sb_ui_unlock.c' if args.sb_unlock_library else
                'host-input/host_ui_unlock.c' if args.unlock_ui else 'host-input/host_swipe.c')
(out / 'host_swipe.c').write_bytes(source.read_bytes())
if args.statusbar_with_unlock:
    with (out / 'host_swipe.c').open('ab') as combined:
        combined.write(b'\n' + (DEV / 'host-input/statusbar_1080.c').read_bytes())
if args.idle_policy_with_unlock:
    with (out / 'host_swipe.c').open('ab') as combined:
        if args.idle_policy_disable:
            combined.write(b'\n#define ODIN_IDLE_DISABLE_POLICY 1\n')
        if args.idle_policy_system:
            combined.write(b'\n#define ODIN_SYSTEM_IDLE_POLICY 1\n')
        if args.idle_policy_assertion:
            combined.write(b'\n#define ODIN_IDLE_ASSERTION_POLICY 1\n')
        combined.write(b'\n' + (DEV / 'host-input/sb_idle_policy.c').read_bytes())
if args.gpu_surface_probe:
    with (out / 'host_swipe.c').open('ab') as combined:
        combined.write(b'\n' + (DEV / 'host-input/OdinSurfaceImport.h').read_bytes().replace(b'#pragma once', b''))
        for name in ('OdinSurfaceImport.c', 'gpu_surface_probe.c'):
            combined.write(b'\n' + (DEV / 'host-input' / name).read_bytes().replace(b'#include "OdinSurfaceImport.h"', b''))
system = ['dispatch_queue_create', 'sleep', 'usleep', 'dprintf', 'mach_absolute_time', 'dyld_stub_binder']
cf = ['CFStringCreateWithCString', 'CFStringGetCString', 'CFDictionaryCreateMutable', 'CFDictionarySetValue', 'CFDictionaryGetValue',
      'CFNumberCreate', 'CFNumberGetValue', 'CFNumberGetTypeID', 'CFArrayCreate', 'CFRetain', 'CFRelease', 'CFEqual', 'CFGetTypeID', 'CFBooleanGetTypeID',
      'CFBooleanGetValue', 'kCFBooleanTrue', 'kCFTypeDictionaryKeyCallBacks', 'kCFTypeDictionaryValueCallBacks',
      'kCFTypeArrayCallBacks']
hid = ['IOHIDEventSystemClientCreateWithType', 'IOHIDEventSystemClientScheduleWithDispatchQueue',
       'IOHIDVirtualServiceClientCreateWithCallbacks', 'IOHIDVirtualServiceClientRemove',
       'IOHIDVirtualServiceClientDispatchEvent', 'IOHIDEventCreateDigitizerEvent',
       'IOHIDEventCreateDigitizerFingerEvent', 'IOHIDEventCreateKeyboardEvent', 'IOHIDEventAppendEvent', 'IOHIDEventSetIntegerValue']
objc = []
surface = []
if args.unlock_ui or args.sb_unlock_library:
    contract = json.loads((DEV / 'build/display-analysis-ios16/u56-verified-unlock-contract.json').read_text())
    assert contract['passed'] and contract['target'] == 'iOS16.5/20F66'
    system = ['dlopen', 'dlerror', 'dprintf', 'exit', 'dispatch_main', 'dispatch_time',
              'dispatch_after_f', 'dispatch_get_global_queue', 'dyld_stub_binder', '_NSConcreteGlobalBlock']
    cf, hid = [], []
    objc = ['objc_getClass', 'sel_registerName', 'objc_msgSend', 'class_getInstanceMethod']
if args.sb_unlock_library:
    methods = {m['selector']: m for m in json.loads((DEV / 'build/display-analysis-ios16/u59-sb-lock-manager.json').read_text())[0]['methods']}
    assert methods['isUILocked']['types'] == 'B16@0:8'
    assert methods['unlockUIFromSource:withOptions:']['types'] == 'B28@0:8i16@20'
    system = ['open', 'dprintf', 'close', 'getpid', 'dispatch_time', 'dispatch_after_f', '_dispatch_main_q', 'dyld_stub_binder']
    objc += ['class_getClassMethod']
if args.statusbar_library or args.statusbar_with_unlock:
    if args.statusbar_library:
        system, cf, hid, objc = ['open', 'dprintf', 'close', 'dyld_stub_binder'], [], [], ['objc_getClass', 'sel_registerName', 'objc_msgSend']
    system += ['free']
    objc += ['object_getClass', 'class_getSuperclass', 'class_copyMethodList', 'method_getName',
             'method_getImplementation', 'method_getTypeEncoding', 'class_replaceMethod']
if args.idle_policy_with_unlock:
    system += ['sysctlbyname']
    if args.idle_policy_assertion:
        cf += ['CFStringCreateWithCString', 'CFRelease']
        objc += ['objc_retain', 'objc_release']
    contracts = [('u85-uiapplication', 'setIdleTimerDisabled:', 'v20@0:8B16'),
                 ('u85-springboard-app', 'resetIdleTimerAndUndim', 'v16@0:8'),
                 ('u85-backlight', 'screenIsOn', 'B16@0:8'),
                 ('u85-backlight', 'isDigitizerDisabled', 'B16@0:8')]
    if args.idle_policy_system:
        contracts += [('u85-backlight', 'preventIdleSleep', 'v16@0:8'),
                      ('u85-backlight', 'allowIdleSleep', 'v16@0:8')]
    if args.idle_policy_assertion:
        contracts += [('u85-idle-coordinator', 'acquireIdleTimerDisableAssertionForReason:', '@24@0:8@16'),
                      ('u85-idle-coordinator', 'isIdleTimerDisabled', 'B16@0:8'),
                      ('u85-idle-coordinator', '_hasIdleTimerDisableAssertions', 'B16@0:8'),
                      ('u85-idle-coordinator', '_areIdleTimerDisableAssertionsPrevented', 'B16@0:8')]
    for file, selector, types in contracts:
        methods = json.loads((DEV / ('build/display-analysis-ios16/' + file + '.json')).read_text())[0]['methods']
        assert next(m for m in methods if m['selector'] == selector)['types'] == types
if args.gpu_surface_probe:
    system += ['dispatch_get_global_queue', 'mach_task_self', 'mach_continuous_time', 'mach_timebase_info']
    cf += ['CFDictionaryCreateMutable', 'CFDictionarySetValue', 'CFNumberCreate',
           'kCFTypeDictionaryKeyCallBacks', 'kCFTypeDictionaryValueCallBacks']
    hid += ['IOServiceGetMatchingService', 'IOServiceMatching', 'IOServiceOpen', 'IOServiceClose',
            'IOObjectRelease', 'IOConnectCallStructMethod', 'IOConnectMapMemory64', 'IOConnectUnmapMemory64']
    surface = ['IOSurfaceCreate', 'IOSurfaceLookup', 'IOSurfaceGetBaseAddress', 'IOSurfaceGetAllocSize',
               'IOSurfaceGetWidth', 'IOSurfaceGetHeight', 'IOSurfaceGetBytesPerRow', 'IOSurfaceGetPlaneCount',
               'IOSurfaceGetPixelFormat', 'IOSurfaceGetID', 'IOSurfaceLock', 'IOSurfaceUnlock']
c = Cache(DEFAULT)
mangled = lambda name: name if name == 'dyld_stub_binder' else '_' + name
needed = {mangled(name) for name in system + cf + hid + objc + surface}
found = {}
for image in c.images:
    if not ('/IOKit.framework/' in image.name or image.name.endswith(('CoreFoundation.framework/CoreFoundation', 'IOSurface.framework/IOSurface'))
            or '/system/libsystem_' in image.name or image.name.endswith(('/libdispatch.dylib', '/libdyld.dylib', '/libobjc.A.dylib'))):
        continue
    if not image.exports:
        continue
    trie = image.file_bytes(*image.exports)
    todo = [(0, '')]
    while todo:
        at, name = todo.pop()
        size, start = uleb(trie, at)
        end = start + size
        if size:
            flags, pos = uleb(trie, start)
            if name in needed:
                assert not flags & 8, (name, 'Re-export needs its own origin audit')
                value, pos = uleb(trie, pos)
                found.setdefault(name, []).append(dict(image=image.name, address=hex(image.base + value), actual_export=True))
        count, pos = trie[end], end + 1
        for _ in range(count):
            stop = trie.find(b'\0', pos)
            edge = trie[pos:stop].decode()
            child, pos = uleb(trie, stop + 1)
            todo.append((child, name + edge))
assert needed == found.keys(), sorted(needed - found.keys())
c.close()
for name, install, symbols in [('libSystem.tbd', '/usr/lib/libSystem.B.dylib', system),
                             ('CoreFoundation.tbd', '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation', cf),
                             ('IOKit.tbd', '/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit', hid),
                             ('objc.tbd', '/usr/lib/libobjc.A.dylib', objc),
                             ('IOSurface.tbd', '/System/Library/Frameworks/IOSurface.framework/IOSurface', surface)]:
    if not symbols:
        continue
    text = ('--- !tapi-tbd-v3\narchs: [ arm64 ]\nplatform: ios\ninstall-name: ' + install + '\n'
            'exports:\n  - archs: [ arm64 ]\n    symbols: [ ' + ', '.join(mangled(s) for s in symbols) + ' ]\n...\n')
    (out / name).write_bytes(text.encode('utf8'))
subprocess.run([*SSH, 'mkdir -p ' + remote], check=True)
subprocess.run([*SCP, str(out / 'host_swipe.c'), *map(str, out.glob('*.tbd')), 'odin@127.0.0.1:' + remote + '/'], check=True)
compile_args = ['clang-18', '-target', 'arm64-apple-ios16.5', '-std=c11', '-O1', '-ffreestanding',
                '-fno-stack-protector', '-Wall', '-Wextra', '-Werror', '-c', remote + '/host_swipe.c', '-o', remote + '/host_swipe.o']
if args.unlock_ui:
    compile_args.append('-fblocks')
link_args = ['ld64.lld-18', '-arch', 'arm64', '-platform_version', 'ios', '16.5', '16.5', '-adhoc_codesign',
             '-e', '_main', '-o', remote + '/host_swipe', remote + '/host_swipe.o',
             *[remote + '/' + path.name for path in sorted(out.glob('*.tbd'))]]
if args.sb_unlock_library or args.statusbar_library:
    entry = link_args.index('-e')
    del link_args[entry:entry + 2]
    link_args += ['-dylib', '-install_name', '/redwood/host-input/' + ('libodin-statusbar.dylib' if args.statusbar_library else 'libodin-ui-unlock.dylib')]
for command in (compile_args, link_args):
    result = subprocess.run([*SSH, ' '.join(command)], capture_output=True, text=True, timeout=60)
    (out / ('compile.log' if command is compile_args else 'link.log')).write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
entitlements = {'com.apple.private.hid.client.event-dispatch': True} if with_entitlement else {}
if args.unlock_ui:
    entitlements = {'com.apple.springboard.requestDeviceUnlock': True}
if entitlements:
    signer = DEV / 'research/github-setup-20261104/ldid_linux_x86_64'
    assert hashlib.sha256(signer.read_bytes()).hexdigest() == '4b8862b2fefa2cd7fa8f88cb0310779619aeaa8c72d6aff22f019b470f2fa99a'
    entitlement_path = out / 'host_swipe.entitlements'
    entitlement_path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run([*SCP, str(entitlement_path), 'odin@127.0.0.1:' + remote + '/'], check=True)
    result = subprocess.run([*SSH, '/home/odin/unixnu-odin-build/evidence/ldid_linux_x86_64 -S' +
        remote + '/host_swipe.entitlements ' + remote + '/host_swipe'], capture_output=True, text=True, timeout=60)
    (out / 'sign.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    extracted = subprocess.run([*SSH, '/home/odin/unixnu-odin-build/evidence/ldid_linux_x86_64 -e ' +
        remote + '/host_swipe'], capture_output=True, timeout=60, check=True).stdout
    assert plistlib.loads(extracted) == entitlements
    (out / 'extracted-entitlements.plist').write_bytes(extracted)
subprocess.run([*SCP, 'odin@127.0.0.1:' + remote + '/host_swipe', str(out / 'host_swipe')], check=True)
audit = audit_file((out / 'host_swipe').read_bytes(), '/redwood/host-input/host_swipe')
assert audit['code_directories'] and all(not row['page_hash_mismatches'] for row in audit['code_directories'])
if entitlements:
    data = (out / 'host_swipe').read_bytes()
    signature = next(row for row in audit['load_commands'] if row['command'] == '0x1d')['offset']
    count = struct.unpack_from('>I', data, signature + 8)[0]
    blobs = {}
    for i in range(count):
        slot, relative = struct.unpack_from('>II', data, signature + 12 + 8 * i)
        at = signature + relative
        size = struct.unpack_from('>I', data, at + 4)[0]
        blobs[slot] = data[at:at + size]
    assert struct.unpack_from('>I', blobs[5])[0] == 0xfade7171
    assert plistlib.loads(blobs[5][8:]) == entitlements
    for slot, cd in blobs.items():
        if struct.unpack_from('>I', cd)[0] != 0xfade0c02:
            continue
        hash_offset, = struct.unpack_from('>I', cd, 16)
        special, = struct.unpack_from('>I', cd, 24)
        size, kind = struct.unpack_from('>2B', cd, 36)
        assert special >= 5
        algorithm = {1: 'sha1', 2: 'sha256', 3: 'sha256', 4: 'sha384'}[kind]
        assert cd[hash_offset - 5 * size:hash_offset - 4 * size] == hashlib.new(algorithm, blobs[5]).digest()[:size]
(out / 'tool-audit.json').write_text(json.dumps([audit], indent=2) + '\n')
record = dict(scope='Host-only virtual input; physical touch unqualified', source=str(source),
    source_sha256=hashlib.sha256((out/'host_swipe.c').read_bytes()).hexdigest(), original_ios16_imports=found,
    compile=compile_args, link=link_args, signed_macho_audit='tool-audit.json',
    device_commands_executed=False, kernel_unchanged=True, runtime_verified=False,
    icon_desktop_verified=False, entitlements=entitlements,
    entitlement_blob_and_special_slot_verified=bool(entitlements),statusbar_with_unlock=args.statusbar_with_unlock,
    idle_policy_with_unlock=args.idle_policy_with_unlock,idle_policy_disable=args.idle_policy_disable,
    idle_policy_system=args.idle_policy_system,
    idle_policy_assertion=args.idle_policy_assertion,
    gpu_surface_probe=args.gpu_surface_probe,
    tool_kind='statusbar-library' if args.statusbar_library else 'sb-unlock-library' if args.sb_unlock_library else 'unlock-ui' if args.unlock_ui else 'virtual-input')
(out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
