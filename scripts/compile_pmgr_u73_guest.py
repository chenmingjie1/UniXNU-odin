"""Compile the iOS16 original-nub bridge and enable the existing BSD hook."""
from pathlib import Path
import hashlib, json, shutil, subprocess

root = Path('/home/odin/unixnu-odin-build')
up = root/'upstream'
out = root/'evidence/odin-pmgr-u73'
record = json.loads((up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
source = out/'OdinPlatformPower.cpp'
obj = out/'OdinPlatformPower.o'
command = []
arguments = record['arguments']
i = 0
while i < len(arguments):
    arg = arguments[i]
    if arg == record['file']:
        command.append(str(source))
    elif arg == '-o':
        command += ['-o', str(obj)]
        i += 1
    elif arg in ('-MF', '-MJ'):
        i += 1
    elif arg == '-Xclang' and arguments[i+1].startswith('-W'):
        i += 1
    elif not arg.startswith(('-W', '--ld-path=')) and arg not in ('-MD', '-MP', '-w'):
        command.append(arg)
    i += 1
command += ['-I', str(up/'build/storage-abi/include'),
    '-I', str(up/'.cache/xnu-work/osfmk'), '-include',
    str(root/'evidence/odin-storage-abi-u12/odin-ios-target.h'),
    '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
    '-Wno-deprecated-declarations', '-Wno-c99-designator', '-Wno-reorder-init-list',
    '-Wno-deprecated-enum-enum-conversion', '-Wno-missing-field-initializers']
(out/'compile-command.json').write_text(json.dumps(command, indent=2)+'\n')
r = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True)
(out/'compile.log').write_text(r.stdout+r.stderr)
if r.returncode: raise SystemExit(r.stdout+r.stderr)
archive = out/'libOdinPlatformPower.a'
subprocess.run([shutil.which('llvm-ar') or 'ar', 'rcs', archive, obj], check=True)
tree = up/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
bsd = tree/'bsd/DEVELOPMENT/bsd_init.o'
if bsd.exists():
    shutil.copy2(bsd, out/'bsd_init.o.before')
    bsd.unlink()
link = (root/'evidence/odin-virtual-timer-u72/link_kernel.sh').read_text()
link = link.replace('evidence/odin-virtual-timer-u72', 'evidence/odin-pmgr-u73')
link = link.replace('archives="', 'archives="-Wl,-force_load,'+str(archive)+' ', 1)
link = link.replace('bash build_offline_kernel.sh \\\n',
                    'bash build_offline_kernel.sh \\\n  bsd_init.o_CFLAGS_ADD=-DXNU_SHENG_PMGR=1 \\\n')
assert 'bsd_init.o_CFLAGS_ADD=-DXNU_SHENG_PMGR=1' in link
(out/'link_kernel.sh').write_text(link)
subprocess.run(['bash', str(out/'link_kernel.sh')], check=True)
kernel = tree/'mach.development.bcm2837.unstripped'
shutil.copy2(kernel, out/'native-real-iig.macho')
(out/'build-receipt.json').write_text(json.dumps(dict(
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    native_kernel_sha256=hashlib.sha256(kernel.read_bytes()).hexdigest(),
    bridge='original provider-less iOS16 ApplePMGRNub; no SoC power backend',
    original_apple_executable_modified=False, phone_tested=False), indent=2)+'\n')
subprocess.run(['tar', '-czf', str(out/'guest-evidence.tgz'), '-C', str(out),
    'OdinPlatformPower.cpp', 'OdinPlatformPower.o', 'libOdinPlatformPower.a',
    'compile-command.json', 'compile.log', 'link_kernel.sh',
    'kernel-link.log', 'kernel-crypto-seal.log', 'build-receipt.json',
    'native-real-iig.macho'], check=True)
print('PMGR bridge compiled and source XNU linked; original Apple driver remains unchanged')
