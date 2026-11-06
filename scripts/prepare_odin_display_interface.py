"""Generate the version-qualified opaque display superclass and annotation.

The annotation is never linked or executed. It lets the real source compiler
check the class extent and all 338 dispatch entries before backend porting.
Unknown private methods have no usable source-level calling contract.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'work/UniXNU-odin'
AUDIT = DEV/'build/display-analysis-ios16/dispatch-discovery.json'
audit = json.loads(AUDIT.read_text())
protocol_path = DEV/'build/display-analysis-ios16/protocol-static-audit.json'
protocol = json.loads(protocol_path.read_text())
assert protocol['candidate_sha256'] == audit['candidate_sha256']
assert protocol['dimension_slot'] == 246 and protocol['hardware_start_slot'] == 274
assert protocol['dimension_fields'] == dict(width=5208,height=5212)
legacy = next(t for t in audit['dispatch_candidates'] if t.get('name') == 'IOMobileFramebufferLegacy')
assert audit['target_os'] == 'iOS 16.5 / 20F66' and legacy['entries'] == 338
assert legacy['instance_bytes'] == 0x1660
dot_pitch=json.loads((DEV/'build/display-owner-u16/dot-pitch-qualification.json').read_text())
assert dot_pitch['passed'] and dot_pitch['provider_slot']==188
assert legacy['methods'][188]['address']==dot_pitch['original_method']
assert dot_pitch['output_bytes']==4 and dot_pitch['missing_property_return']=='0xe00002f0'
out = DEV/'drivers/OdinDisplay'
out.mkdir(exist_ok=True)
header = '''// Generated from the exact original iOS 16.5 / 20F66 family.
// Opaque ABI storage, never source access to guessed private offsets.
#pragma once
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <libkern/libkern.h>
struct OriginalLegacyStateRequest {
 uint32_t skipDisplay,display,skipPower,power;
 uint8_t suppressApply,reserved[3];
};
static_assert(sizeof(OriginalLegacyStateRequest)==20,"Original state request extent");
extern "C" void odin_original_request_state(IOService *,const void *,uint32_t);
class IOMobileFramebufferLegacy : public IOService {
 OSDeclareAbstractStructors(IOMobileFramebufferLegacy)
 unsigned char originalPrivate[0x1660-sizeof(IOService)];
public:
 uint32_t logicalScheduling() const {
  uint32_t value=0;memcpy(&value,reinterpret_cast<const unsigned char *>(this)+5236,4);return value;
 }
 uint32_t logicalScanoutPower() const {
  uint32_t value=0;memcpy(&value,reinterpret_cast<const unsigned char *>(this)+5240,4);return value;
 }
 const void *readySwapRequest() const {
  // Original submit moves pending +4896 to ready +4880 before slot276.
  const void *value=nullptr;memcpy(&value,reinterpret_cast<const unsigned char *>(this)+4880,8);return value;
 }
 bool activateOnlyReadySwap(const void *request) {
  // Exact iOS16 queue operations in the original selection/completion code.
  // Transfer the sole family-owned pending reference; do not invent a retain.
  auto base=reinterpret_cast<unsigned char *>(this);
  const void *current=nullptr,*pending=nullptr,*head=nullptr,*tail=nullptr,*next=nullptr,*previous=nullptr;
  memcpy(&current,base+4872,8);memcpy(&pending,base+4896,8);
  memcpy(&head,base+4880,8);memcpy(&tail,base+4888,8);
  if(!request || current || pending || head!=request)return false;
  auto bytes=reinterpret_cast<unsigned char *>(const_cast<void *>(request));
  memcpy(&next,bytes+2408,8);memcpy(&previous,bytes+2416,8);
  if(next || previous!=base+4880 || tail!=bytes+2408)return false;
  const void *empty=nullptr,*newTail=base+4880;
  memcpy(base+4880,&empty,8);memcpy(base+4888,&newTail,8);
  memcpy(bytes+2408,&empty,8);memcpy(bytes+2416,&empty,8);
  memcpy(base+4872,&request,8);
  odin_original_request_state(this,request,3);
  return true;
 }
 void installBootDimensions(uint32_t width,uint32_t height) {
  auto bytes=reinterpret_cast<unsigned char *>(this);
  memcpy(bytes+5208,&width,sizeof(width));
  memcpy(bytes+5212,&height,sizeof(height));
 }
 void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 IOReturn setProperties(OSObject *) override;
 void systemWillShutdown(IOOptionBits) override;
 IOService *probe(IOService *,SInt32 *) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 IOWorkLoop *getWorkLoop() const override;
 IOReturn newUserClient(task_t,void *,UInt32,IOUserClient **) override;
 IOReturn setPowerState(unsigned long,IOService *) override;
'''
for i in range(168, legacy['entries']):
    if i == 188:
        header += ' virtual IOReturn getDotPitch(uint32_t *);\n'
    elif i == 246:
        header += ' virtual void getDisplayDimensions(uint32_t *,uint32_t *);\n'
    elif i == 274:
        header += ' virtual bool startHardware();\n'
    elif i == 282:
        header += ' virtual bool validateSwap(const void *);\n'
    elif i == 276:
        header += ' virtual void kickSwapQueue();\n'
    elif i == 281:
        header += ' virtual void completeCurrentSwap();\n'
    elif i == 321:
        header += ' virtual IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t)=0;\n'
    elif i == 212:
        header += ' virtual IOReturn queryOutput64(uint32_t,uint32_t *,void *)=0;\n'
    elif i == 336:
        header += ' virtual IOReturn applyStateRequest(const OriginalLegacyStateRequest *,bool);\n'
    elif i in legacy['abstract_slots']:
        header += f' virtual __attribute__((noreturn)) void unclassified{i}()=0;\n'
    else:
        header += f' virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified{i}();\n'
header += '};\nstatic_assert(sizeof(IOMobileFramebufferLegacy)==0x1660,"iOS16.5 original class extent");\n'
(out/'OriginalLegacyFramebufferABI.h').write_text(header)
annotation = '''// Compiler annotation only: never linked, registered or executed.
#include "OriginalLegacyFramebufferABI.h"
#include <IOKit/IOLib.h>
class OdinDisplayABIAnnotation : public IOMobileFramebufferLegacy {
 OSDeclareDefaultStructors(OdinDisplayABIAnnotation)
public:
'''
for i in legacy['abstract_slots']:
    if i==212:
        annotation += ' IOReturn queryOutput64(uint32_t,uint32_t *,void *) override { panic("Annotation-only iOS16 display slot 212"); }\n'
    elif i==321:
        annotation += ' IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t) override { panic("Annotation-only iOS16 display slot 321"); }\n'
    else:
        annotation += f' __attribute__((noreturn)) void unclassified{i}() override {{ panic("Unqualified iOS16 display slot {i}"); }}\n'
annotation += '''};
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
'''
(out/'OdinDisplayABIAnnotation.cpp').write_text(annotation)
contract = dict(scope='Compiler annotation only; no display backend or publication',
    target_os=audit['target_os'], original_kernel_sha256=audit['original_sha256'],
    candidate_sha256=audit['candidate_sha256'], audit_sha256=hashlib.sha256(AUDIT.read_bytes()).hexdigest(),
    protocol_audit_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
    original_family_text_sha256=audit['original_family_text_sha256'],
    expected_entries=338, instance_bytes=0x1660, abstract_slots=legacy['abstract_slots'],
    protected_constructor=legacy['protected_constructor'], base_destructor=legacy['base_destructor'],
    vtable=legacy['vtable'], metaclass=legacy['metaclass'],
    expected_dispatch=legacy['methods'], runtime_verified=False,
    device_commands_executed=False, desktop_verified=False)
(out/'interface-contract.json').write_text(json.dumps(contract, indent=2)+'\n')
# README contains runtime state and is maintained separately from this ABI generator.
print('Generated iOS16.5 display interface and non-runtime compiler annotation')
