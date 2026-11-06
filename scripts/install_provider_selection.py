"""Select one crypto provider in the isolated native/prelinked build.

The original prelinked crypto module can register before EARLY_BOOT. Keep its
completed registration instead of installing the source fallback a second time.
Do not change either provider's POST or the kernel's duplicate-registration
assertion. This script has no device operations.
"""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

root = Path('/home/odin/unixnu-odin-build')
tree = root / 'upstream/.cache/xnu-work'
out = root / 'evidence/odin-provider-u09'
out.mkdir(exist_ok=False)
source = tree / 'osfmk/prng/prng_random.c'
before = source.read_text()
shutil.copy2(source, out / 'prng_random.c.before')
shutil.copy2(root / 'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped', out / 'native-before.macho')
needle = 'SECURITY_READ_ONLY_LATE(kern_return_t) source_corecrypto14_status = KERN_FAILURE;'
assert before.count(needle) == 1
text = before.replace(needle, needle + '''
/* 0: not selected; 1: an earlier provider; 2: the source fallback. */
SECURITY_READ_ONLY_LATE(unsigned int) source_corecrypto14_provider = 0;
extern bool crypto_init;
''')
needle = '\tinfo.address = (vm_address_t)&_mh_execute_header;'
assert text.count(needle) == 1
text = text.replace(needle, '''
	/* OSKext startup precedes EARLY_BOOT. A prelinked crypto module may have
	 * already completed POST and installed both interfaces by this point.
	 * Never weaken register_and_init_prng's duplicate-install assertion.
	 */
	if (prng_ready) {
		if (!crypto_init) {
			panic("existing PRNG has no registered crypto interface");
		}
		source_corecrypto14_provider = 1;
		source_corecrypto14_status = KERN_SUCCESS;
		return;
	}
	if (crypto_init) {
		panic("crypto provider registration incomplete: no PRNG");
	}
	source_corecrypto14_provider = 2;
''' + needle)
source.write_text(text)
patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='a/osfmk/prng/prng_random.c', tofile='b/osfmk/prng/prng_random.c'))
(out / 'odin-provider-selection.patch').write_text(patch)
(out / 'verification.json').write_text(json.dumps({
    'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
    'post_disabled': False, 'duplicate_registration_assertion_changed': False,
    'existing_provider_requires': ['prng_ready', 'crypto_init'],
    'source_fallback_retained': True, 'device_commands_executed': False,
}, indent=2) + '\n')
print('Single-provider selection installed; full native rebuild required')
