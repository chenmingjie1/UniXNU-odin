"""Compile/test an original-IOSurface userptr adapter, without phone operations.

No desktop renderer is installed by this build. Its ABI is the public IOSurface
C interface and the already-existing board user-memory GPU selector, not a
MiniIOSurface layout or an original-kext private method.
"""
from pathlib import Path
import hashlib
import json
import subprocess
from build_odin_display_owner import SSH, SCP
from inspect_cache_objc_refs import Cache, DEFAULT
from inspect_root_exec import audit_file
from symbolicate_ios_stacks import uleb

D = Path(__file__).resolve().parents[1]
OUT = D / 'build/gpu-surface-import'
REMOTE = '/home/odin/unixnu-odin-build/evidence/odin-gpu-surface-import'
for command in (SSH, SCP):
    command[command.index('-i') + 1] = str(D / 'build/touch-metal-u74/guest-ssh-key')


def main():
    OUT.mkdir(exist_ok=True)
    imports = {
        '/System/Library/Frameworks/IOSurface.framework/IOSurface': [
            'IOSurfaceLookup', 'IOSurfaceGetBaseAddress', 'IOSurfaceGetAllocSize',
            'IOSurfaceGetWidth', 'IOSurfaceGetHeight', 'IOSurfaceGetBytesPerRow',
            'IOSurfaceGetPlaneCount', 'IOSurfaceGetPixelFormat', 'IOSurfaceGetID',
            'IOSurfaceLock', 'IOSurfaceUnlock'],
        '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation': ['CFRelease'],
        '/usr/lib/system/libdyld.dylib': ['dyld_stub_binder'],
    }
    mangle = lambda name: name if name == 'dyld_stub_binder' else '_' + name
    wanted = {mangle(n) for names in imports.values() for n in names}
    found = {}
    cache = Cache(DEFAULT)
    try:
        for image in cache.images:
            if image.name not in imports:
                continue
            trie = image.file_bytes(*image.exports)
            todo = [(0, '')]
            while todo:
                at, name = todo.pop()
                length, start = uleb(trie, at)
                end = start + length
                if length and name in wanted:
                    flags, pos = uleb(trie, start)
                    assert not flags & 8, 'Re-export requires its own origin audit'
                    value, pos = uleb(trie, pos)
                    found[name] = dict(image=image.name, address=hex(image.base + value))
                count, pos = trie[end], end + 1
                for _ in range(count):
                    stop = trie.index(0, pos)
                    edge = trie[pos:stop].decode()
                    child, pos = uleb(trie, stop + 1)
                    todo.append((child, name + edge))
    finally:
        cache.close()
    assert found.keys() == wanted, sorted(wanted - found.keys())
    stubs = []
    for install, names in imports.items():
        stub = OUT / (install.rsplit('/', 1)[1] + '.tbd')
        stub.write_bytes(('--- !tapi-tbd-v3\narchs: [ arm64 ]\nplatform: ios\ninstall-name: '
                         + install + '\nexports:\n  - archs: [ arm64 ]\n    symbols: [ '
                         + ', '.join(mangle(n) for n in names) + ' ]\n...\n').encode())
        stubs.append(stub)
    files = [D / 'host-input/OdinSurfaceImport.c', D / 'host-input/OdinSurfaceImport.h',
             D / 'tests/surface_import_test.c', *stubs]
    subprocess.run([*SSH, 'mkdir -p ' + REMOTE], check=True)
    subprocess.run([*SCP, *map(str, files), 'odin@127.0.0.1:' + REMOTE + '/'], check=True)
    commands = [
        ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
         '-fsanitize=address,undefined', REMOTE + '/OdinSurfaceImport.c',
         REMOTE + '/surface_import_test.c', '-I' + REMOTE, '-o', REMOTE + '/test'],
        [REMOTE + '/test'],
        ['clang-18', '-target', 'arm64-apple-ios16.5', '-std=c11', '-ffreestanding',
         '-fno-stack-protector', '-Wall', '-Wextra', '-Werror', '-O2', '-c',
         REMOTE + '/OdinSurfaceImport.c', '-o', REMOTE + '/OdinSurfaceImport.o'],
        ['ld64.lld-18', '-arch', 'arm64', '-platform_version', 'ios', '16.5', '16.5',
         '-adhoc_codesign', '-dylib', '-install_name', '/redwood/gpu/libodin-surface-import.dylib',
         '-o', REMOTE + '/libodin-surface-import.dylib', REMOTE + '/OdinSurfaceImport.o',
         *[REMOTE + '/' + p.name for p in stubs]],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run([*SSH, ' '.join(command)], capture_output=True, text=True, timeout=60)
        (OUT / f'{index:02d}.log').write_text(result.stdout + result.stderr)
        assert not result.returncode, result.stdout + result.stderr
    artifact = OUT / 'libodin-surface-import.dylib'
    subprocess.run([*SCP, 'odin@127.0.0.1:' + REMOTE + '/' + artifact.name, str(artifact)], check=True)
    audit = audit_file(artifact.read_bytes(), '/redwood/gpu/' + artifact.name)
    assert audit['filetype'] == 6 and audit['code_directories']
    assert all(not row['page_hash_mismatches'] for row in audit['code_directories'])
    (OUT / 'macho-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    record = dict(scope='original IOSurface userspace-to-userptr adapter only',
        target='iOS16.5/20F66 arm64', exports=found,
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        commands=commands, ownership_bounds_failure_tests_passed=True,
        address_and_undefined_sanitizers_passed=True, signed_macho_verified=True,
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files[:3]},
        physical_surface_import_verified=False, desktop_gpu_composition_verified=False,
        metal_plugin_integrated=False, device_commands_executed=False)
    (OUT / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k not in ('commands', 'exports')}, indent=2))


if __name__ == '__main__':
    main()
