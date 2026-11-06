#!/usr/bin/env bash
set -euo pipefail
cd /home/odin/unixnu-odin-build
ROOT=$PWD/upstream
export PATH=$PWD/bin:$PATH UNIXNU_IOS_VERSION=16.5
python3 build_pthread_archive_import.py > evidence/pthread.log 2>&1
archives="-Wl,-force_load,/home/odin/unixnu-odin-build/evidence/odin-gpu-u85/libOdinAdreno.a -Wl,-force_load,/home/odin/unixnu-odin-build/evidence/odin-touch-u75/libOdinStTouch.a -Wl,-force_load,/home/odin/unixnu-odin-build/evidence/odin-pmgr-u73/libOdinPlatformPower.a -Wl,-force_load,/home/odin/unixnu-odin-build/evidence/odin-display-owner-u82/libOdinDisplay.a -L/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk/usr/local/lib/kernel -lfirehose_kernel $ROOT/build/corecrypto-2023/libcorecrypto_kernel_noasm-namespaced.a"
for p in armdt-platform/libArmDTPlatform.a armcpu/libArmCpu.a libpthread-kernel/libpthread_kernel.a ram-block/libRamBlock.a; do
  test -f "$ROOT/build/$p"
  archives="$archives -Wl,-force_load,$ROOT/build/$p"
done
python3 - <<'PY'
from pathlib import Path
root=Path('/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837')
stamp=root/'.odin-native-arch-timer'
if not stamp.exists():
    (root/'osfmk/DEVELOPMENT/start.o').unlink(missing_ok=True)
    stamp.write_text('1\n')
PY
python3 - <<'PY'
from pathlib import Path
import shutil
p=Path('/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped')
b=Path('/home/odin/unixnu-odin-build/evidence/odin-gpu-u85/kernel-before-relink.macho')
if p.exists():
    if not b.exists():shutil.copy2(p,b)
    p.unlink()
PY
python3 - <<'PY'
from pathlib import Path
p=Path('/home/odin/unixnu-odin-build/upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/pexpert/DEVELOPMENT/pe_init.o')
p.unlink(missing_ok=True)
for rel in ('osfmk/DEVELOPMENT/arm_init.o','osfmk/DEVELOPMENT/arm_vm_init.o'):
    (p.parents[2]/rel).unlink(missing_ok=True)
PY
bash build_offline_kernel.sh \
  bsd_init.o_CFLAGS_ADD=-DXNU_SHENG_PMGR=1 \
  pe_init.o_CFLAGS_ADD=-DXNU_DT_PANIC_REGION=1 \
  LD_KERNEL_LIBS="$ROOT/build/cc-kext-llvm14/libcc_kext.a" \
  LD_KERNEL_ARCHIVES="$archives" start.o_SFLAGS_ADD=-DXNU_NATIVE_ARCH_TIMER=1 \
  startup.o_CFLAGS_ADD=-DXNU_NATIVE_TRUST_CACHE=1 \
  ubc_subr.o_CFLAGS_ADD=-DXNU_NATIVE_CS_HASH_CACHE=1 \
  KernelConfigTables.cpo_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1 \
  kern_exec.o_CFLAGS_ADD='-DXNU_ODIN_DISPLAY_OWNER=1 -DXNU_OWNER_DATA_MOUNT=1 -DXNU_OWNER_BOOT_MANIFEST=1 -DXNU_NATIVE_RAM_BLOCK=1' \
  > evidence/odin-gpu-u85/kernel-link.log 2>&1
python3 "$ROOT/scripts/seal-source-crypto-kernel.py" \
  "$ROOT/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped" \
  > evidence/odin-gpu-u85/kernel-crypto-seal.log 2>&1
