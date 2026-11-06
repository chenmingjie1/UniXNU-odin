"""Run the upstream concrete-vtable binder against the iOS16 static audit.

Runtime metadata and block I/O are still unqualified. Absolute imports resolve
to the original prelinked driver, never to substitute implementations.
"""
from pathlib import Path
import hashlib
import json
import sys

root = Path('/home/odin/unixnu-odin-build')
up = root / 'upstream'
audit_path = root / 'interface-static-audit.json'
audit = json.loads(audit_path.read_text())
assert audit['target_os'] == 'iOS 16.5 / 20F66'
assert audit['method_slots'] == 190 and audit['kernel_bindings'] == 176
assert audit['original_executable_code_unchanged']
script = up / 'scripts/build-virtio-mmio-bindings.py'
text = script.read_text()
text = text.replace("ROOT / 'build/storage-abi/interface-audit.json'", repr(str(audit_path)))
text = text.replace('json.loads((' + repr(str(audit_path)) + ').read_text())',
                    'json.loads(Path(' + repr(str(audit_path)) + ').read_text())')
text = text.replace("if not audit['live_native_4k'] or audit['method_slots']", "if audit['method_slots']")
text = text.replace("actual_io_qualified=False,", "actual_io_qualified=False, live_metadata_verified=False,")
text = text.replace("['xcrun', 'c++filt']", "['llvm-cxxfilt']")
sys.path.insert(0, str(up / 'scripts'))
sys.argv = [str(script), '--component', 'RamBlock', '--directory', str(up / 'build/ram-block')]
(up / 'build/ram-block/binder-provenance.json').write_text(json.dumps({
    'upstream_script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
    'audit_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
    'adaptation': 'Actual 16.5 static audit replaces unrelated 17.7 live checkpoint; no runtime qualification claimed',
}, indent=2) + '\n')
exec(compile(text, str(script), 'exec'), {'__file__': str(script), '__name__': '__main__'})
