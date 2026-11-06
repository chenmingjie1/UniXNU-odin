"""Independently verify actual final display dispatch and late registration."""
from pathlib import Path
import argparse,hashlib,json,struct,sys

ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'work/UniXNU-odin'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--tag',default='u16')
a=p.parse_args();assert a.tag.isalnum()
OUT=DEV/('build/display-owner-'+a.tag)
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

def symbols(blob,image):
    at=next(at for cmd,at,_ in image['commands'] if cmd==2)
    off,count,strings,size=struct.unpack_from('<4I',blob,at+8)
    result=[]
    for i in range(count):
        ix,kind,section,desc,value=struct.unpack_from('<IBBHQ',blob,off+i*16)
        assert ix<size
        name=blob[strings+ix:blob.index(b'\0',strings+ix,strings+size)].decode()
        result.append(dict(name=name,kind=kind,section=section,value=value))
    return result

contract=json.loads((DEV/'drivers/OdinDisplay/interface-contract.json').read_text())
obj=(OUT/'OdinLegacyGOPDisplay.o').read_bytes();oi=np.macho(obj);syms=symbols(obj,oi)
table=next(s['value'] for s in syms if s['name']=='__ZTV20OdinLegacyGOPDisplay')
relocations={}
for segment in oi['segments']:
    for section in segment['sections']:
        if section['va']<=table<section['va']+section['size']:
            ro,rc=struct.unpack_from('<II',obj,section['command_offset']+56)
            for i in range(rc):
                address,bits=struct.unpack_from('<II',obj,ro+i*8)
                if bits>>27&1 and bits>>28==0 and bits>>25&3==3:
                    relocations[section['va']+address]=syms[bits&0xffffff]['name']
methods=[relocations.get(table+16+i*8) for i in range(338)]
assert all(methods) and table+16+338*8 not in relocations
native=(OUT/'native-real-iig.macho').read_bytes();ni=np.macho(native)
names={s['name']:s['value'] for s in symbols(native,ni) if not s['kind']&0xe0 and s['kind']&0x0e}
candidate=(OUT/'kernel.prelinked.experimental.macho').read_bytes();ci=np.macho(candidate)
vtable=names['__ZTV20OdinLegacyGOPDisplay']
offset=np.backed_offset(ci['segments'],vtable+16,338*8,len(candidate))
actual=struct.unpack_from('<338Q',candidate,offset)
own=[];original=[];inherited=[]
for slot,(method,value,expected) in enumerate(zip(methods,actual,contract['expected_dispatch'])):
    assert names[method]==value,(slot,method,hex(value),hex(names[method]))
    if 'OdinLegacyGOPDisplay' in method:
        assert slot in [0,1,7,14,87,155,188,274,276,282]+contract['abstract_slots']
        own.append(slot)
    elif 'IOMobileFramebufferLegacy' in method:
        assert value==int(expected['address'],16),(slot,method)
        original.append(slot)
    else:
        assert slot<168 and method in expected['kernel_names'],(slot,method)
        inherited.append(slot)
late=(OUT/'OdinLegacyGOPDisplay.late.o').read_bytes();li=np.macho(late)
assert not any(s['name']=='__mod_init_func' for g in li['segments'] for s in g['sections'])
init=next(s for s in symbols(late,li) if s['name']=='__GLOBAL__sub_I_OdinLegacyGOPDisplay.cpp')
assert init['kind']&1 and init['section']
def text(blob,image):
    sec=next(s for g in image['segments'] for s in g['sections'] if s['name']=='__text')
    return blob[sec['fileoff']:sec['fileoff']+sec['size']]
assert text(obj,oi)==text(late,li)
assert '_odin_display_owner_start' in names and '__GLOBAL__sub_I_OdinLegacyGOPDisplay.cpp' in names
result=dict(passed=True,checked_final_dispatch_entries=338,owned_slots=own,
    original_slots=len(original),native_inherited_slots=len(inherited),
    initializer_exported=True,automatic_initializer_removed=True,late_init_instructions_unchanged=True,
    native_sha256=hashlib.sha256(native).hexdigest(),candidate_sha256=hashlib.sha256(candidate).hexdigest(),
    scope='Final linked bytes, not runtime or phone qualification',desktop_verified=False,device_commands_executed=False)
keyobj=OUT/'OdinKeyStoreEvents.o'
if '_odin_surface_inspections' in names:
    surface=json.loads((DEV/'build/display-analysis-ios16/u25-surface-contract.json').read_text())
    assert surface['passed']
    for name,entry in surface['getters'].items():
        assert names['_odin_surface_'+name]==int(entry['address'],16)
    # Independently match actual compiler-generated source memory calls with
    # the original IOSurface's getLength/prepare/complete dispatch offsets.
    for name,expected in [
        ('length',(0xf9400008,0xf9405901,0xd61f0020)),
        ('prepare',(0xf9400008,0xf9406d02,0x52800001,0xd61f0040)),
        ('complete',(0xf9400008,0xf9407102,0x52800001,0xd61f0040))]:
        off=np.backed_offset(ci['segments'],names['_odin_memory_'+name+'_contract'],len(expected)*4,len(candidate))
        assert struct.unpack_from('<'+'I'*len(expected),candidate,off)==expected,name
    result['surface_accessors']={'qualified':True,'source_memory_dispatch_matches':True,
        'descriptor_field':56,'format_field':164,'validator_slot':282,
        'presentation_implemented':False,'runtime_surface_seen':False}
if keyobj.exists():
    ko=keyobj.read_bytes();ki=np.macho(ko)
    kl=(OUT/'OdinKeyStoreEvents.late.o').read_bytes();kli=np.macho(kl)
    assert not any(s['name']=='__mod_init_func' for g in kli['segments'] for s in g['sections'])
    initname='__GLOBAL__sub_I_OdinKeyStoreEvents.cpp'
    initializer=next(s for s in symbols(kl,kli) if s['name']==initname)
    assert initializer['kind']&1 and initializer['section']
    assert text(ko,ki)==text(kl,kli)
    for name in (initname,'_odin_keyevents_start','_odin_keyevents_stage','__ZTV13AppleKeyStore'):
        assert name in names,name
        if name=='_odin_keyevents_stage':
            assert any(s['va']<=names[name] and names[name]+4<=s['va']+s['size'] for s in ci['segments'])
        else:
            np.backed_offset(ci['segments'],names[name],8,len(candidate))
    result['keyevents_initializer']={
        'automatic_initializer_removed':True,'exported':True,
        'instructions_unchanged':True,'final_symbols_present':True,
        'runtime_qualified':False}
(OUT/'display-link-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
