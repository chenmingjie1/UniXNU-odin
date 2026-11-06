"""Fetch pinned GLES source into research; never installs it on the phone.

Git blob verification also lets an identical local HakiOS checkout supply files.
No binary, firmware, SDK or system image is fetched by this script.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import urllib.request

REPO = 'HeliumStudio-Dev/hackios-xnu-kernel'
PIN = '57722468a3774e2ec60017705ec356ae9b31f40e'
FILES = {
    'devices/raphael/README.md', 'devices/raphael/device.conf', 'docs/RAPHAEL.md',
    'tools/mk-mesa.sh', 'userland/mkeagl.py', 'userland/build.sh',
    'userland/src/eagl.c', 'userland/src/gl_osmesa.c',
    'userland/src/hakios.gl.h', 'userland/src/eagl_slots.txt',
    'userland/src/inject.c', 'xnu-env.sh', 'xnu-deps/setup.sh',
}


def api(resource):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + resource,
                                    headers={'User-Agent': 'UniXNU-odin-source-review'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-upstream', type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'research/helium-20261106'
    root.mkdir(parents=True, exist_ok=True)
    tree_path = root / 'tree.json'
    tree = json.loads(tree_path.read_text()) if tree_path.exists() else api('git/trees/' + PIN + '?recursive=1')
    assert tree['sha'] == PIN and not tree.get('truncated'), 'Incomplete or unpinned reference'
    tree_path.write_text(json.dumps(tree, indent=2) + '\n')
    rows = []
    for entry in tree['tree']:
        name = entry['path']
        if entry['type'] != 'blob' or not (name in FILES or name.startswith('tools/mesa/')):
            continue
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        target = root / 'source' / name
        candidates = [target]
        if options.local_upstream:
            candidates.append(options.local_upstream / name)
        data = None
        for candidate in candidates:
            if candidate.is_file():
                value = candidate.read_bytes()
                if blob_sha(value) == entry['sha']:
                    data = value
                    break
        if data is None:
            remote = api('git/blobs/' + entry['sha'])
            assert remote['encoding'] == 'base64'
            data = base64.b64decode(remote['content'])
        assert blob_sha(data) == entry['sha'] and len(data) == entry['size'], name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append(dict(path=name, git_blob=entry['sha'], bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest()))
    assert FILES <= {row['path'] for row in rows}
    manifest = dict(repository='https://github.com/' + REPO, commit=PIN, files=rows,
                    scope='Verified source reference only; no device validation or installation')
    (root / 'gles-source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(commit=PIN, verified_files=len(rows), directory=str(root))))


if __name__ == '__main__':
    main()
