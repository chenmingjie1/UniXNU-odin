#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/odin/unixnu-odin-build/upstream
OLD=/home/odin/xnu-work/project
export THEOS=/home/odin/xnu-work/theos
export XNUDEPS=$OLD/xnu-deps
export PATH=$XNUDEPS/host/bin:$PATH
export XNU_SDK_PATH=$XNUDEPS/sdk/iPhoneOS16.5.xnu.sdk
export XNU_SDK_VERSION=16.5
export XNU_PLATFORM_PATH=$XNUDEPS/sdk/Platforms/iPhoneOS.platform
export KERNEL_SDKROOT=$XNU_SDK_PATH
export XNU_AVAILABILITY_PL=$XNUDEPS/AvailabilityVersions/availability.pl
# The original bootstrap shim emitted empty implementations and RPC stubs.
# Use the audited XNU8796 generated sources when that stage is available.
if [ -x /home/odin/unixnu-odin-build/iig-tools/iig-8796-cached ]; then
  export IIG=/home/odin/unixnu-odin-build/iig-tools/iig-8796-cached
fi
cd "$ROOT"
python3 scripts/linux/prepare-xnu.py source
mkdir -p build/xnu/ios-obj build/xnu/ios-sym build/xnu/ios-dst
# This is the bootstrap pass: real compilation records precede provider archives.
# External providers are added by the final pass; no unresolved-link output is a
# deployable kernel. The SDK/toolchain paths are existing measured Linux inputs.
exec make -C .cache/xnu-work build SDKROOT=iphoneos ARCH_CONFIGS=ARM64 \
  MACHINE_CONFIGS=BCM2837 KERNEL_CONFIGS=DEVELOPMENT \
  ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64 LARGE_MEMORY_DEFINE=-UARM_LARGE_MEMORY \
  ARM64_LINK_ADDR=0xfffffff007004000 ARM64_PLKSEG_ADDR=0xfffffff004004000 \
  DEPLOYMENT_TARGET_FLAGS='-miphoneos-version-min=16.5 -DXNU_TARGET_OS_IOS' \
  DEPLOYMENT_LINKER_FLAGS='-Wl,-ios_version_min,16.5' \
  RC_DARWIN_KERNEL_VERSION=22.5.0 RC_ProjectSourceVersion=8796.101.5 \
  BUILD_LTO=0 BUILD_WERROR=0 DO_CTFMERGE=0 BUILD_DSYM=0 MAKEJOBS=-j4 \
  HOST_CC="clang -include $XNUDEPS/hostinc/hostcompat.h -I$XNUDEPS/hostinc -Wno-unused-command-line-argument -Wno-error=implicit-function-declaration" \
  HOST_FLEX=flex HOST_BISON=bison HOST_GM4=m4 CC=/home/odin/unixnu-odin-build/record-clang CXX=/home/odin/unixnu-odin-build/record-clang++ LOGCOLORS=n \
  XCRUN="$XNUDEPS/host/bin/xcrun" HOST_CODESIGN=true \
  PLUTIL="$XNUDEPS/host/bin/plutil" \
  OTHER_CFLAGS='-march=armv8.1-a -DXNU_SOURCE_CORECRYPTO14=1 -DXNU_NATIVE_PAN=1 -DXNU_BOOT_PROGRESS=0 -mllvm -disable-atexit-based-global-dtor-lowering' \
  TIGHTBEAMC=tightbeamc-not-supported \
  MEMORY_SIZE=4294967296 SYSCTL_HW_PHYSICALCPU=4 SYSCTL_HW_LOGICALCPU=4 \
  OBJROOT="$ROOT/build/xnu/ios-obj" SYMROOT="$ROOT/build/xnu/ios-sym" DSTROOT="$ROOT/build/xnu/ios-dst" "$@"
