"""Check state query contracts in the unmodified iOS16.5 AppleKeyStore framework."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];DEV=ROOT/'work/UniXNU-odin'
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
c=Cache(DEFAULT)
word=lambda at:struct.unpack('<I',c.read(at,4))[0]
def check(at,expected):assert word(at)==expected,(hex(at),hex(word(at)),hex(expected))
def branch(at):
    w=word(at);assert w&0xfc000000==0x94000000
    imm=w&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    return at+imm*4
def add_pair(at):
    a,b,d=struct.unpack('<3I',c.read(at,12))
    assert a&0x9f00001f==0x90000010 and b&0xffc003ff==0x91000210 and d==0xd61f0200
    imm=((a>>29)&3)|(((a>>5)&0x7ffff)<<2)
    if imm&(1<<20):imm-=1<<21
    return (at&~4095)+(imm<<12)+((b>>10)&4095)
movw=lambda reg,value:0x52800000|(value<<5)|reg
calls=[(0,0x1f22c99e0,0x1f22c99fc),(7,0x1f22d439c,0x1f22d43ac),
    (14,0x1f22d4748,0x1f22d4754),(17,None,0x1f22d740c),(35,None,0x1f22d740c)]
for selector,at,call in calls:
    if at is not None:check(at,movw(1,selector))
    assert c.resolve(add_pair(branch(call)))['symbol']=='_IOConnectCallMethod'
# No-argument handshake: all scalar/struct input and output addresses/counts zero.
for reg in range(2,8):check(0x1f22c99e4+(reg-2)*4,(0x52800000 if reg==3 else 0xd2800000)|reg)
check(0x1f22c99dc,0xa9007fff)
# Scalar outputs are uint64 at sp+24, returned count initialized to one.
for at in (0x1f22d4384,0x1f22d4728):check(at,movw(8,1))
check(0x1f22d43a0,movw(3,1))
check(0x1f22d4730,0x710002bf) # cmp w21,#0
check(0x1f22d4734,0x1a9f07e3) # cset w3,ne
# State wrappers both select one-input, zero-scalar-output struct call helper.
check(0x1f22d7368,movw(1,17));check(0x1f22d7470,movw(1,35))
check(0x1f22d73f8,movw(3,1))
for reg in range(4,8):check(0x1f22d73fc+(reg-4)*4,0xd2800000|reg)
# The returned struct is passed at its returned size into the original DER decoder.
assert branch(0x1f22d7424)==0x1f22c673c
windows=[(0x1f22c9938,0xf4),(0x1f22d433c,0xc0),(0x1f22d46e0,0xc4),(0x1f22d7364,0x114)]
kernel=(DEV/'build/ios16-prelink/kernelcache.decompressed').read_bytes()
client=b'AppleKeyStoreUserClient\0site.AppleKeyStoreUserClient\0'
offset=kernel.find(client);assert offset>=0 and kernel.find(client,offset+1)<0
record=dict(passed=True,target='iOS16.5/20F66',
    contracts=[dict(selector=0,input_scalars=0,output_scalars=0,struct_bytes=0),
        dict(selector=7,input_scalars=1,output_scalars=1),
        dict(selector=14,input_scalars='0 if bag is zero, otherwise 1',output_scalars=1),
        dict(selector=[17,35],input_scalars=1,output_scalars=0,output_struct='DER, parsed by original decoder')],
    call_target='_IOConnectCallMethod',
    instruction_windows=[dict(address=hex(at),bytes=size,sha256=hashlib.sha256(c.read(at,size)).hexdigest()) for at,size in windows],
    state_semantics='Ephemeral RAM-only context. No keybag, passcode, key operations or encrypted storage.',
    unsupported_operations_preserved=True,device_tested=False,desktop_verified=False)
record['original_sandbox_client_name']=dict(name='AppleKeyStoreUserClient',original_file_offset=hex(offset),
    matched_bytes_sha256=hashlib.sha256(client).hexdigest(),unique_match=True,
    original_kernel_sha256=hashlib.sha256(kernel).hexdigest(),policy_disabled=False)
c.close()
out=DEV/'build/display-analysis-ios16/u23-aks-state-contract.json'
out.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
