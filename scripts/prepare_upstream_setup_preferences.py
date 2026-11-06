"""Extract a bounded development setup policy from pinned ios-fuxi source.

Read upstream code as AST data, never execute it. Do not copy its activation,
watchdog, executable, or launchd changes. The resulting file only provisions
a copy of host QEMU Data, and does not prove real setup has completed.
"""
from pathlib import Path
import ast
import hashlib
import json
import struct
from inspect_cache_objc_refs import Cache, DEFAULT, pointer, cstring

DEV = Path(__file__).resolve().parents[1]
source = DEV / 'research/github-setup-20261104/sweet-root-tweaks-9b34af2.py'
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'b0f7b42b53cb48c97cc20c302132ce0a4a076c2170442b56fb9b957abaf2a13b'
main = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
preferences = {}
for node in ast.walk(main):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'merge_pref':
        continue
    domain = ast.literal_eval(node.args[1])
    if domain == 'com.apple.purplebuddy':
        preferences[domain] = ast.literal_eval(node.args[2])
    elif domain == 'com.apple.purplebuddy.notbackedup':
        value = node.args[2]
        assert isinstance(value, ast.DictComp) and ast.literal_eval(value.value) is False
        assert len(value.generators) == 1 and not value.generators[0].ifs
        assert isinstance(value.key, ast.Name) and value.key.id == value.generators[0].target.id
        preferences[domain] = {key: False for key in ast.literal_eval(value.generators[0].iter)}
    elif domain == 'com.apple.springboard':
        policy = ast.literal_eval(node.args[2])
        preferences[domain] = {'MCForceShowCloudConfigurationUI': policy['MCForceShowCloudConfigurationUI']}
assert preferences['com.apple.purplebuddy'] == dict(SetupDone=True, SetupFinishedAllSteps=True, SetupVersion=11, daemonizeNeedsToRun=False)
assert len(preferences) == 3

# Qualify the original iOS16.5 completed-setup reader independently of the
# upstream iOS image. This does not assert all upstream keys are sufficient.
c = Cache(DEFAULT)
assert cstring(c, pointer(c, 0x1d7f8ab90 + 16)) == 'SetupFinishedAllSteps'
assert cstring(c, pointer(c, 0x1d7f8a190 + 16)) == 'com.apple.purplebuddy'
call, stub = 0x1a3aa0608, 0x1a93de59c
word = struct.unpack('<I', c.read(call, 4))[0]
imm = word & 0x3ffffff
if imm & (1 << 25):
    imm -= 1 << 26
assert word & 0xfc000000 == 0x94000000 and call + 4 * imm == stub
adrp, add, branch = struct.unpack('<3I', c.read(stub, 12))
assert adrp & 0x9f00001f == 0x90000010 and add & 0xffc003ff == 0x91000210 and branch == 0xd61f0200
imm = ((adrp >> 29) & 3) | (((adrp >> 5) & 0x7ffff) << 2)
if imm & (1 << 20):
    imm -= 1 << 21
target = (stub & ~4095) + (imm << 12) + ((add >> 10) & 4095)
assert c.resolve(target)['symbol'] == '_CFPreferencesGetAppBooleanValue'
c.close()
record = dict(scope='Host development setup provisioning',
    source='https://github.com/bangprovn/ios-fuxi/blob/9b34af2f635535fc9771ad41182fd72ed0650d8e/tools/sweet-root-tweaks.py',
    source_sha256=hashlib.sha256(raw).hexdigest(), upstream_code_executed=False,
    preferences=preferences, original_ios16_reader=dict(address=hex(call), target=hex(target),
        symbol='_CFPreferencesGetAppBooleanValue', domain='com.apple.purplebuddy', key='SetupFinishedAllSteps'),
    all_keys_sufficient_unverified=True, real_setup_completed_claim=False,
    activation_changes_copied=False, watchdog_changes_copied=False,
    device_commands_executed=False)
output = DEV / 'build/root-media/setup-preferences-u49.json'
assert not output.exists()
output.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
