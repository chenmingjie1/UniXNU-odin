// Compiler annotation only: never linked, registered or executed.
#include "OriginalLegacyFramebufferABI.h"
#include <IOKit/IOLib.h>
class OdinDisplayABIAnnotation : public IOMobileFramebufferLegacy {
 OSDeclareDefaultStructors(OdinDisplayABIAnnotation)
public:
 __attribute__((noreturn)) void unclassified211() override { panic("Unqualified iOS16 display slot 211"); }
 IOReturn queryOutput64(uint32_t,uint32_t *,void *) override { panic("Annotation-only iOS16 display slot 212"); }
 __attribute__((noreturn)) void unclassified242() override { panic("Unqualified iOS16 display slot 242"); }
 __attribute__((noreturn)) void unclassified243() override { panic("Unqualified iOS16 display slot 243"); }
 __attribute__((noreturn)) void unclassified292() override { panic("Unqualified iOS16 display slot 292"); }
 __attribute__((noreturn)) void unclassified293() override { panic("Unqualified iOS16 display slot 293"); }
 IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t) override { panic("Annotation-only iOS16 display slot 321"); }
 __attribute__((noreturn)) void unclassified322() override { panic("Unqualified iOS16 display slot 322"); }
 __attribute__((noreturn)) void unclassified329() override { panic("Unqualified iOS16 display slot 329"); }
};
OSDefineMetaClassAndStructors(OdinDisplayABIAnnotation,IOMobileFramebufferLegacy)
static_assert(sizeof(OdinDisplayABIAnnotation)==0x1660,"Annotation adds no fields");
static_assert(sizeof(IOExternalMethodDispatch)==24,"Actual dispatch row ABI");
static_assert(sizeof(IOExternalMethodArguments)==248,"Actual user-client argument ABI");
#define CHECK_FIELD(type,member,offset) static_assert(__builtin_offsetof(type,member)==offset,"Actual compiler field: " #type "." #member)
CHECK_FIELD(IOExternalMethodDispatch,function,0);
CHECK_FIELD(IOExternalMethodDispatch,checkScalarInputCount,8);
CHECK_FIELD(IOExternalMethodDispatch,checkStructureInputSize,12);
CHECK_FIELD(IOExternalMethodDispatch,checkScalarOutputCount,16);
CHECK_FIELD(IOExternalMethodDispatch,checkStructureOutputSize,20);
CHECK_FIELD(IOExternalMethodArguments,scalarInput,32);
CHECK_FIELD(IOExternalMethodArguments,scalarInputCount,40);
CHECK_FIELD(IOExternalMethodArguments,structureInput,48);
CHECK_FIELD(IOExternalMethodArguments,structureInputSize,56);
CHECK_FIELD(IOExternalMethodArguments,scalarOutput,72);
CHECK_FIELD(IOExternalMethodArguments,scalarOutputCount,80);
CHECK_FIELD(IOExternalMethodArguments,structureOutput,88);
CHECK_FIELD(IOExternalMethodArguments,structureOutputSize,96);
#undef CHECK_FIELD
