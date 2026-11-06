"""Stage the existing RamBlock with isolated, volatile host Data selection."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil
import tarfile

root = Path(__file__).resolve().parents[3]
dev = root / 'work/UniXNU-odin'
src = root / 'work/UniXNU-components/RamBlock-4be2d7eb05ef5a98126c91e0302c149140c0e3e1'
dst = dev / 'drivers/RamBlock'
shutil.copytree(src, dst, dirs_exist_ok=True)
before = (src / 'NativeRamBlock.cpp').read_text()
after = '#include "OdinIOSTarget.h"\n' + before
anchor = '  if (!IOBlockStorageDevice::start(provider)) return false;'
assert after.count(anchor) == 1
after = after.replace(anchor, '''  uint32_t enabled = 0;
  if (!PE_parse_boot_argn("odin-data-mount", &enabled, sizeof(enabled)) || enabled != 1) return false;
''' + anchor)
after = after.replace('"PackedRAMDisk"', '"OdinDataPackedRAMDisk"').replace('"RAMDisk"', '"OdinDataRAMDisk"')
after = after.replace('  registerService();\n  return true;',
    '  IOLog("NativeRamBlock: isolated odin Data online, %llu bytes\\n", logical);\n  registerService();\n  return true;')

# The static kernel linker cannot leave weak provider imports unresolved.
# Compile out the optional persistence feature; never add fake UFS callbacks.
def guard_region(start, end):
    global after
    first = after.index(start)
    last = after.index(end, first)
    after = after[:first] + '#if !ODIN_RAM_VOLATILE_ONLY\n' + after[first:last] + '#endif\n' + after[last:]

guard_region('unsigned native_ufs_store_mode(void)', '// Diagnostics. state:')
guard_region('  struct StoreOps {', 'public:\n')
first = after.index('    if (!gate) return;\n', after.index('  void attachStore()'))
last = after.index('\n  }\n\n  bool available()', first)
after = after[:first] + '#if !ODIN_RAM_VOLATILE_ONLY\n' + after[first:last] + '\n#endif' + after[last:]
first = after.index('    if(direct){\n', after.index('IOReturn NativeRamBlock::doAsyncReadWrite'))
last = after.index('    if(write)__atomic_fetch_add(&native_ram_block_writes', first)
original_optional = after[first:last]
after = after[:first] + '#if !ODIN_RAM_VOLATILE_ONLY\n' + original_optional + '''#else
    actual=ramSparseIO(sparse,write,block*512,bytes,ops,noMemory);
#endif
''' + after[last:]
(dst / 'NativeRamBlock.cpp').write_text(after)
(dst / 'OdinIOSTarget.h').write_text('''#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wmacro-redefined"
#include <TargetConditionals.h>
#pragma clang diagnostic pop
#undef TARGET_OS_OSX
#undef TARGET_OS_IPHONE
#undef TARGET_OS_IOS
#undef TARGET_OS_EMBEDDED
#define TARGET_OS_OSX 0
#define TARGET_OS_IPHONE 1
#define TARGET_OS_IOS 1
#define TARGET_OS_EMBEDDED 1
#define ODIN_RAM_VOLATILE_ONLY 1
''')
patch_dir = dev / 'patches/ram-block'
patch_dir.mkdir(exist_ok=True)
(patch_dir / 'odin-data-descriptor.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True),
    fromfile='a/NativeRamBlock.cpp', tofile='b/NativeRamBlock.cpp')))
(dst / 'odin-adaptation.json').write_text(json.dumps({
    'revision': '4be2d7eb05ef5a98126c91e0302c149140c0e3e1',
    'source_sha256': hashlib.sha256(before.encode()).hexdigest(),
    'adapted_sha256': hashlib.sha256(after.encode()).hexdigest(),
    'scope': 'Host separate volatile RAM Data; persistent UFS feature excluded',
    'device_commands_executed': False,
}, indent=2) + '\n')
archive = dev / 'build/native-kernel/ram-block-odin-u12.tar.gz'
with tarfile.open(archive, 'w:gz') as stream:
    for path in sorted(dst.iterdir()):
        if path.is_file():
            stream.add(path, arcname='RamBlock/' + path.name)
print('Staged separate RAM Data provider; optional UFS persistence excluded')
