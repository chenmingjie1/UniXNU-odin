"""Inspect final prelinked bytes independently of emission and FAT packaging."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import tarfile
import argparse

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'work/UniXNU-odin/build/ios16-prelink'
INPUT=OUT
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input-dir',type=Path,default=OUT)
OUT=parser.parse_args().input_dir
sys.path.insert(0,str(ROOT/'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'))
import native_prelink as np

original=(INPUT/'kernelcache.decompressed').read_bytes()
native=(OUT/'native-real-iig.macho').read_bytes()
candidate=(OUT/'kernel.prelinked.experimental.macho').read_bytes()
report=json.loads((OUT/'prelink-emission-report.json').read_text())
images={name:np.macho(data) for name,data in [('original',original),('native',native),('candidate',candidate)]}
digest=lambda blob:hashlib.sha256(blob).hexdigest()
assert digest(original)==report['original_sha256']
assert digest(native)==report['native_sha256']
assert digest(candidate)==report['candidate_sha256']

def read(data,image,va,size):
    offset=np.backed_offset(image['segments'],va,size,len(data))
    return data[offset:offset+size]

for binding in report['bindings']:
    value,=struct.unpack('<Q',read(candidate,images['candidate'],binding['new_site'],8))
    assert value==binding['new_target'],binding

def metadata(data,image):
    seg=next(s for s in image['segments'] if s['name']=='__PRELINK_INFO')
    parsed=np.unserialize_xml(read(data,image,seg['va'],seg['filesize']))
    return {e['CFBundleIdentifier']:e for e in parsed['_PrelinkInfoDictionary']}

before=metadata(original,images['original'])
after=metadata(candidate,images['candidate'])
policy=report.get('board_metadata_policy')
if policy:
    for disabled in policy['disabled_personalities']:
        name=disabled['bundle']; personality=disabled['personality']
        assert before[name]['IOKitPersonalities'][personality]==disabled['original']
        assert personality not in after[name]['IOKitPersonalities']
    for name in before.keys() & after.keys():
        expected=dict(before[name].get('IOKitPersonalities',{}))
        for disabled in policy['disabled_personalities']:
            if disabled['bundle']==name:expected.pop(disabled['personality'])
        assert after[name].get('IOKitPersonalities',{})==expected,name
text_checked=[]
for name,expected in report['original_executable_sha256'].items():
    old_module=np.macho(original,np.backed_offset(images['original']['segments'],before[name]['_PrelinkExecutableLoadAddr'],32,len(original)))
    old_text=next(s for s in old_module['segments'] if s['name']=='__TEXT_EXEC')
    a=read(original,images['original'],old_text['va'],old_text['filesize'])
    b=read(candidate,images['candidate'],old_text['va']+report['slide'],old_text['filesize'])
    assert a==b and digest(b)==expected,name
    assert after[name]['_PrelinkExecutableLoadAddr']==before[name]['_PrelinkExecutableLoadAddr']+report['slide']
    text_checked.append(name)
assert len(text_checked)==30
assert 'com.apple.iokit.IOHIDEventDriver' in after
assert not after['com.apple.iokit.IOHIDEventDriver'].get('_PrelinkExecutableLoadAddr')

symbols={name:va for va,names in np.exports(native,images['native']).items() for name in names}
required=['__ZN9IOService12Start_InvokeE5IORPCP15OSMetaClassBasePFiS2_PS_E',
          '__ZN9IOService11Stop_InvokeE5IORPCP15OSMetaClassBasePFiS2_PS_E',
          '__ZN8OSObject8DispatchE5IORPC']
code={}
for name in required:
    assert name in symbols,name
    code[name]={'native_va':hex(symbols[name]),'first_32_bytes':read(native,images['native'],symbols[name],32).hex()}

archive=INPUT/'native-iig-evidence-20261103.tar.gz'
assert digest(archive.read_bytes())=='2500d7429239795055a71e704622bc5c9f0232b6d89a9ef1acc9ce2bbf597df8'
with tarfile.open(archive) as t:
    v=json.load(t.extractfile('iig-tools/native8796/verification.json'))
    assert len(v['results'])==17
    for row in v['results']:
        assert row['compile_returncode']==row['generator_returncode']==0
        data=t.extractfile('iig-tools/native8796/generated/'+row['name']+'.iig.cpp').read()
        assert digest(data)==row['adapted_source_sha256']
        assert b'__iig_stub_' not in data and b'stand-in for iig' not in data
        assert b'sizeof(IORPC) == 24' in data
result={'passed':True,'candidate_sha256':digest(candidate),'native_sha256':digest(native),
        'original_sha256':digest(original),'actual_pointer_values_checked':len(report['bindings']),
        'original_executable_kexts_byte_identical':text_checked,
        'hid_event_driver_codeless_entry_present':True,
        'real_iig_implementations_compiled':17,'iorpc_bytes_compile_asserted':24,
        'required_real_rpc_exports':code,'iig_evidence_archive_sha256':digest(archive.read_bytes()),
        'abi_qualified':False,'device_tested':False,'runtime_qualified':False}
(OUT/'independent-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS:',len(report['bindings']),'actual pointers, 30 unchanged kext text ranges, 17 real IIG implementations; runtime unqualified')
