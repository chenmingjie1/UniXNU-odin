"""Linux: compile real IIG output for XNU8796 in an isolated staging directory.

DriverKit440 uses a cached kernelContent field absent from the original
XNU8796 IORPC. Recover content from its Mach message exactly as IOUserServer
does, preserving the original 24-byte by-value IORPC ABI. Keep SDK256 class
declarations, and require every generated implementation to compile against
them. This does not install or link the staged objects.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path('/home/odin/unixnu-odin-build')
SRC = ROOT / 'upstream/.cache/xnu-work'
OBJ = ROOT / 'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT'
OUT = ROOT / 'iig-tools/native8796'
OUT.mkdir(exist_ok=True)
GENERATED = OUT / 'generated'
GENERATED.mkdir(exist_ok=True)
HEADERS = OUT / 'headers'
for name in ('IOKit', 'DriverKit'):
    dest = HEADERS / name / 'IORPC.h'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes((ROOT / 'xnu-reference/iokit' / name / 'IORPC.h').read_bytes())


def adapt(text):
    # Typed unions in modern IIG output also carry the optimization. Reading
    # their old message field remains valid under the original 8796 ABI.
    text, typed = re.subn(
        r'const (\w+_Msg_Content) \* messageContent = rpc.kernelContent;',
        r'const \1 * messageContent = reinterpret_cast<const \1 *>(IORPCMessageFromMach(rpc.rpc.message, false));', text)
    text, assigns = re.subn(r'^\s*rpc.kernelContent = &msg->content.__hdr;\n', '\n', text, flags=re.M)
    text, init = re.subn(r', \.kernelContent = &buf.msg.content.__hdr', '', text)
    text = text.replace('rpc.rpc.kernelContent', 'IORPCMessageFromMach(rpc.rpc.message, false)')
    text = text.replace('rpc.kernelContent', 'IORPCMessageFromMach(rpc.message, false)')
    # Drop the cached field from generated typed RPC unions as well.
    text, fields = re.subn(r'^\s*const struct \w+_Msg_Content \* kernelContent;\n', '\n', text, flags=re.M)
    assert 'kernelContent' not in text, 'Unrecognized cached-content access'
    text += '\n#ifdef KERNEL\nstatic_assert(sizeof(IORPC) == 24, "XNU8796 IORPC ABI");\n'
    text += 'static_assert(__builtin_offsetof(IORPC, sendSize) == 16, "IORPC.sendSize ABI");\n'
    text += 'static_assert(__builtin_offsetof(IORPC, replySize) == 20, "IORPC.replySize ABI");\n#endif\n'
    return text, {'typed_reads': typed, 'assignments': assigns, 'initializers': init, 'fields': fields}


results = []
for old_cpp in sorted((OBJ / 'DriverKit').glob('*.iig.cpp')):
    name = old_cpp.name.removesuffix('.iig.cpp')
    spec = SRC / 'iokit/DriverKit' / (name + '.iig')
    record = OBJ / (name + '.iig.cpo.json')
    assert spec.exists() and record.exists(), name
    cpp = GENERATED / old_cpp.name
    command = [str(ROOT / 'iig-tools/iig'), '--def', str(spec), '--header', str(GENERATED / (name+'.h')),
               '--impl', str(cpp), '--framework-name', 'DriverKit', '--',
               *[f'-I{p}' for p in (SRC/'iokit', SRC/'osfmk', SRC/'bsd',
                                  ROOT/'upstream/build/xnu/ios-obj/EXPORT_HDRS', SRC/'EXTERNAL_HEADERS')],
               '-isysroot', '/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk',
               '-x', 'c++', '-std=gnu++1z', '-D__IIG=1', '-DDRIVERKIT_PRIVATE=1', '-DPRIVATE_WIFI_ONLY=1']
    r = subprocess.run(command, capture_output=True, text=True)
    (GENERATED/(name+'.generate.log')).write_text(r.stdout+r.stderr)
    row = {'name': name, 'input_iig_sha256': hashlib.sha256(spec.read_bytes()).hexdigest(),
           'generator_returncode': r.returncode, 'generator_command': command}
    if r.returncode == 0:
        text = cpp.read_text()
        row['unmodified_generated_sha256'] = hashlib.sha256(text.encode()).hexdigest()
        text, row['abi_adapter_counts'] = adapt(text)
        cpp.write_text(text)
        row['adapted_source_sha256'] = hashlib.sha256(cpp.read_bytes()).hexdigest()
        old = json.loads(record.read_text().rstrip().rstrip(','))
        args = old['arguments']
        args[args.index(old['file'])] = str(cpp)
        target = GENERATED / (name+'.iig.cpo')
        args[args.index('-o')+1] = str(target)
        args.insert(1, '-I'+str(HEADERS))
        r = subprocess.run(args, cwd=old['directory'], capture_output=True, text=True)
        (GENERATED/(name+'.compile.log')).write_text(r.stdout+r.stderr)
        row.update(compile_returncode=r.returncode, compile_command=args)
        if r.returncode == 0:
            row['object_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    results.append(row)
    print(name, row.get('compile_returncode', row['generator_returncode']), flush=True)
    (OUT/'verification.json').write_text(json.dumps({
        'generator_commit': 'ea6d147d668ca15d490da638012243fcd705f30d',
        'original_iorpc_bytes': 24, 'results': results,
        'objects_installed': False, 'kernel_linked': False, 'device_tested': False}, indent=2)+'\n')

assert all(r.get('compile_returncode') == 0 for r in results), 'One or more real IIG implementations failed; nothing installed'
print('All', len(results), 'implementations compiled; not installed or linked', flush=True)
