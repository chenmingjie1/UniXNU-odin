"""Use the upstream build entry, excluding the host adapter's blanket -w."""
from pathlib import Path
import hashlib
import json
import sys

root = Path('/home/odin/unixnu-odin-build/upstream')
script = root / 'scripts/build-arm-driver.py'
text = script.read_text()
anchor = "    elif not value.startswith('-W'):\n"
assert text.count(anchor) == 1
text = text.replace(anchor, "    elif value == '-w' or value.startswith('--ld-path='):\n        pass\n" + anchor)
text = text.replace("'-Wno-unnecessary-virtual-specifier', ", '')
text = text.replace("'-Wno-c99-designator',", "'-Wno-c99-designator', '-Wno-missing-field-initializers',")
sys.path.insert(0, str(root / 'scripts'))
sys.argv = [str(script), 'RamBlock']
out = root / 'build/ram-block'
out.mkdir(exist_ok=True)
(out / 'builder-provenance.json').write_text(json.dumps({
    'upstream_script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
    'adaptation': 'Remove host blanket -w and compile-only unused linker selector; retain -Wall -Wextra -Werror',
}, indent=2) + '\n')
exec(compile(text, str(script), 'exec'), {'__file__': str(script), '__name__': '__main__'})
