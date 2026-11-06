// Generated from the exact original iOS 16.5 / 20F66 family.
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
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified168();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified169();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified170();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified171();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified172();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified173();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified174();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified175();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified176();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified177();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified178();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified179();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified180();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified181();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified182();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified183();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified184();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified185();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified186();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified187();
 virtual IOReturn getDotPitch(uint32_t *);
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified189();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified190();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified191();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified192();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified193();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified194();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified195();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified196();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified197();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified198();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified199();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified200();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified201();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified202();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified203();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified204();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified205();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified206();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified207();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified208();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified209();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified210();
 virtual __attribute__((noreturn)) void unclassified211()=0;
 virtual IOReturn queryOutput64(uint32_t,uint32_t *,void *)=0;
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified213();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified214();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified215();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified216();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified217();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified218();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified219();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified220();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified221();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified222();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified223();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified224();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified225();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified226();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified227();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified228();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified229();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified230();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified231();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified232();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified233();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified234();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified235();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified236();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified237();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified238();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified239();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified240();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified241();
 virtual __attribute__((noreturn)) void unclassified242()=0;
 virtual __attribute__((noreturn)) void unclassified243()=0;
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified244();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified245();
 virtual void getDisplayDimensions(uint32_t *,uint32_t *);
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified247();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified248();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified249();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified250();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified251();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified252();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified253();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified254();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified255();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified256();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified257();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified258();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified259();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified260();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified261();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified262();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified263();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified264();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified265();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified266();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified267();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified268();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified269();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified270();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified271();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified272();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified273();
 virtual bool startHardware();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified275();
 virtual void kickSwapQueue();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified277();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified278();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified279();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified280();
 virtual void completeCurrentSwap();
 virtual bool validateSwap(const void *);
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified283();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified284();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified285();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified286();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified287();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified288();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified289();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified290();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified291();
 virtual __attribute__((noreturn)) void unclassified292()=0;
 virtual __attribute__((noreturn)) void unclassified293()=0;
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified294();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified295();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified296();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified297();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified298();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified299();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified300();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified301();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified302();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified303();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified304();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified305();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified306();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified307();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified308();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified309();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified310();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified311();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified312();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified313();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified314();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified315();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified316();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified317();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified318();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified319();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified320();
 virtual IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t)=0;
 virtual __attribute__((noreturn)) void unclassified322()=0;
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified323();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified324();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified325();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified326();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified327();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified328();
 virtual __attribute__((noreturn)) void unclassified329()=0;
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified330();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified331();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified332();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified333();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified334();
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified335();
 virtual IOReturn applyStateRequest(const OriginalLegacyStateRequest *,bool);
 virtual __attribute__((deprecated("Unqualified private ABI; do not call"))) void unclassified337();
};
static_assert(sizeof(IOMobileFramebufferLegacy)==0x1660,"iOS16.5 original class extent");
