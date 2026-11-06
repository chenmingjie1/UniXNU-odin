"""Create a source-only review snapshot, excluding local media and credentials."""
from pathlib import Path
import hashlib
import json
import re
import shutil

D = Path(__file__).resolve().parents[1]
OUT = D / 'publish/UniXNU-odin'
DIRECTORIES = ('drivers', 'firmware', 'host-input', 'package', 'patches',
               'configs', 'dts', 'soc', 'tests', 'scripts', 'docs', 'recipes', 'licenses')
FORBIDDEN = re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE).*PRIVATE KEY|'
                       rb'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|'
                       rb'https?://[^\s"<>]+(?:lhr\.life/t/|trycloudflare\.com/t/)|'
                       rb'https?://[^\s"<>]*[?&]password=')
SUFFIXES = {'.c', '.cpp', '.h', '.py', '.toml', '.json', '.md', '.S', '.sh',
            '.plist', '.dts', '.dtsi', '.patch', '.txt', '.ps1', '.yaml',
            '.yml', '.entitlements', '.diff', '.config', '.inc', '.HakiOS', ''}


def main():
    paths = []
    for name in DIRECTORIES:
        if (D / name).is_dir():
            paths += [p for p in (D / name).rglob('*') if p.is_file()
                      and '__pycache__' not in p.parts and '.git' not in p.parts
                      and p.name != 'OdinTouchRpmhFingerprint.h']
    paths += [D / n for n in ('README.md', 'SOURCE-NOTICE.md', 'source-pins.json',
                              'board.toml', 'feeds.toml', '.gitignore')]
    records = []
    for p in sorted(paths):
        relative = p.relative_to(D)
        assert p.suffix in SUFFIXES or p.name == '.gitignore', relative
        data = p.read_bytes()
        assert len(data) < 1_000_000, relative
        assert b'\0' not in data and not FORBIDDEN.search(data), relative
        assert not any(word in p.name.lower() for word in
                       ('guest-ssh-key', 'private-key', 'credential', 'firmware.c')), relative
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        records.append(dict(path=relative.as_posix(), bytes=len(data),
                            sha256=hashlib.sha256(data).hexdigest()))
    (OUT / 'source-manifest.json').write_text(json.dumps(dict(
        release='u88', scope='source-only development snapshot; not a complete system image',
        files=records), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(directory=str(OUT), files=len(records),
                          total_bytes=sum(p['bytes'] for p in records))))


if __name__ == '__main__':
    main()
