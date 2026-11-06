#pragma clang diagnostic push
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
