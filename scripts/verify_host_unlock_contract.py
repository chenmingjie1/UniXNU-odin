"""Verify the standalone UI request against the actual, unmodified 20F66 cache."""
from pathlib import Path
import hashlib
import json
import struct
from inspect_cache_objc_refs import Cache, DEFAULT, classes, pointer, cstring, stub

DEV = Path(__file__).resolve().parents[1]
c = Cache(DEFAULT)
client = classes(c, '/SpringBoardServices.framework/SpringBoardServices', ['SBSLockScreenService', 'SBSUnlockOptions'])
methods = {m['selector']: m for row in client if row['name'] == 'SBSLockScreenService' for m in row['methods']}
method = methods['requestPasscodeUnlockUIWithOptions:withCompletion:']
assert method['types'] == 'v32@0:8@16@?24'
assert method['implementation'] == '0x191506a64'

def address_add(at):
    a, b = struct.unpack('<2I', c.read(at, 8))
    assert a & 0x9f000000 == 0x90000000
    imm = (a >> 29 & 3) | ((a >> 5 & 0x7ffff) << 2)
    if imm & (1 << 20):
        imm -= 1 << 21
    assert b & 0xffc00000 == 0x91000000 and b >> 5 & 31 == a & 31
    return (at & ~4095) + (imm << 12) + (b >> 10 & 4095)

entitlement_cf = address_add(0x1c4dfa4e8)
assert entitlement_cf == 0x1d9dc12c8
entitlement = cstring(c, pointer(c, entitlement_cf + 16))
assert entitlement == 'com.apple.springboard.requestDeviceUnlock'
provider_slot = (0x1c4dfa4dc & ~4095) + 429711360 + 616
provider = pointer(c, provider_slot)
provider_ro = pointer(c, provider + 32) & ~7
provider_name = cstring(c, pointer(c, provider_ro + 24))
assert provider_name == 'FBServiceClientAuthenticator'
calls = []
for at, expected in [(0x1c4dfa4f4, 'initWithEntitlement:additionalCredentials:'),
                     (0x1c4dfa6b4, 'authenticateAuditToken:error:')]:
    w, = struct.unpack('<I', c.read(at, 4))
    assert w >> 26 == 0x25
    imm = w & 0x3ffffff
    if imm & (1 << 25):
        imm -= 1 << 26
    resolved = stub(c, at + 4 * imm)
    assert resolved['selector'] == expected
    calls.append(dict(call=hex(at), **resolved))
# The external service's connection converts its internal NSError to BOOL.
# Do not mistake the server's object completion for the public completion ABI.
callback = c.read(0x191505bc4, 24)
assert struct.unpack('<6I', callback) == (0xa9422009, 0xf100013f, 0x1a9f17e1,
                                         0xf9400902, 0xaa0803e0, 0xd61f0040)
record = dict(target='iOS16.5/20F66', passed=True, client_methods=client,
              entitlement=entitlement, entitlement_cf=hex(entitlement_cf),
              authenticator_class=provider_name, checked_original_calls=calls,
              public_completion='void (^)(BOOL success)', completion_bridge='0x191505bc4',
              completion_bridge_bytes=callback.hex(),
              server_code_sha256=hashlib.sha256(c.read(0x1c4dfa434, 0x414)).hexdigest(),
              scope='Finite host-only request, no process injection or authentication bypass',
              runtime_success_verified=False, desktop_verified=False, device_commands_executed=False)
c.close()
out = DEV / 'build/display-analysis-ios16/u56-verified-unlock-contract.json'
out.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'client_methods'}, indent=2))
