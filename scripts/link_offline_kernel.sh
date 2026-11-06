#!/usr/bin/env bash
set -euo pipefail
cd /home/odin/unixnu-odin-build
ROOT=$PWD/upstream
export PATH=$PWD/bin:$PATH UNIXNU_IOS_VERSION=16.5
python3 build_pthread_archive_import.py > evidence/pthread.log 2>&1
archives="-L/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk/usr/local/lib/kernel -lfirehose_kernel $ROOT/build/corecrypto-2023/libcorecrypto_kernel_noasm-namespaced.a"
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
bash build_offline_kernel.sh \
  LD_KERNEL_LIBS="$ROOT/build/cc-kext-llvm14/libcc_kext.a" \
  LD_KERNEL_ARCHIVES="$archives" start.o_SFLAGS_ADD=-DXNU_NATIVE_ARCH_TIMER=1 \
  startup.o_CFLAGS_ADD=-DXNU_NATIVE_TRUST_CACHE=1 \
  ubc_subr.o_CFLAGS_ADD=-DXNU_NATIVE_CS_HASH_CACHE=1 \
  KernelConfigTables.cpo_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1 \
  kern_exec.o_CFLAGS_ADD='-DXNU_OWNER_DATA_MOUNT=1 -DXNU_OWNER_BOOT_MANIFEST=1 -DXNU_NATIVE_RAM_BLOCK=1' \
  > evidence/kernel-final.log 2>&1
python3 "$ROOT/scripts/seal-source-crypto-kernel.py" \
  "$ROOT/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped" \
  > evidence/kernel-crypto-seal.log 2>&1
