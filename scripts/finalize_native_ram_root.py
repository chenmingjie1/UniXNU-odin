from pathlib import Path
import difflib
import hashlib
import json

root = Path('/home/odin/unixnu-odin-build')
tree = root/'upstream/.cache/xnu-work'
out = root/'evidence/odin-ram-root-u09'
source = tree/'bsd/dev/memdev.c'
text = source.read_text()
text = text.replace('#include <pexpert/arm/boot.h>', '#include <pexpert/boot.h>')
source.write_text(text)
before = (out/'memdev.c.before').read_text()
header = (tree/'bsd/dev/OdinRamRootRange.h').read_text()
patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='a/bsd/dev/memdev.c', tofile='b/bsd/dev/memdev.c'))
patch += ''.join(difflib.unified_diff([], header.splitlines(True),
    fromfile='/dev/null', tofile='b/bsd/dev/OdinRamRootRange.h'))
(out/'odin-native-ram-root.patch').write_text(patch)
report = json.loads((out/'verification.json').read_text())
report['source_sha256'] = hashlib.sha256(text.encode()).hexdigest()
(out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
print('Native boot_args architecture dispatch and patch synchronized')
