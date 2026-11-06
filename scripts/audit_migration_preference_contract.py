"""Qualify the real iOS16.5 migration preference ABI before host provisioning.

The original reader is not modified. A provisioned build marker intentionally
skips first-boot migration and is never evidence that migration succeeded.
"""
from pathlib import Path
import json
import struct
from inspect_cache_objc_refs import Cache, DEFAULT, pointer, cstring

c=Cache(DEFAULT)
assert cstring(c,pointer(c,0x1da1bc338+16))=='LastSystemVersion'
assert cstring(c,pointer(c,0x1da1bc318+16))=='com.apple.migration'
for at,expected in ((0x1dade89b0,'kCFPreferencesCurrentUser'),
                    (0x1dade89a8,'kCFPreferencesCurrentHost')):
    assert cstring(c,pointer(c,pointer(c,pointer(c,at))+16))==expected

def original_stub_target(at):
    adrp,add,branch=struct.unpack('<3I',c.read(at,12))
    assert adrp&0x9f00001f==0x90000010
    assert add&0xffc003ff==0x91000210 and branch==0xd61f0200
    imm=((adrp>>29)&3)|(((adrp>>5)&0x7ffff)<<2)
    if imm&(1<<20):imm-=1<<21
    return (at&~4095)+(imm<<12)+((add>>10)&4095)

checks={0x1c6b3c674:(0x1ca151b04,'_CFPreferencesSynchronize'),
        0x1c6b3c68c:(0x1ca151ae0,'_CFPreferencesCopyValue'),
        0x1c6b40e60:(0x1ca151af8,'_CFPreferencesSetValue')}
bindings=[]
for call,(stub,symbol) in checks.items():
    word=struct.unpack('<I',c.read(call,4))[0]
    assert word&0xfc000000==0x94000000
    imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert call+4*imm==stub
    target=original_stub_target(stub)
    assert c.resolve(target)['symbol']==symbol
    bindings.append(dict(original_call=hex(call),stub=hex(stub),target=hex(target),symbol=symbol))
assert c.read(0x1c6b3c678,24).hex()=='00b4099000e00c91e10315aae20313aae30314aa1555d894'
record=dict(image='/System/Library/PrivateFrameworks/DataMigration.framework/DataMigration',
    domain='com.apple.migration',key='LastSystemVersion',user='kCFPreferencesCurrentUser',
    host='kCFPreferencesCurrentHost',reader='0x1c6b3c638',writer='0x1c6b40e18',
    original_bindings=bindings,executable_modified=False,device_commands_executed=False,
    scope='Host development provisioning contract; not real migration completion')
c.close()
out=Path(__file__).resolve().parents[1]/'build/display-analysis-ios16/u44-migration-preference-contract.json'
out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
