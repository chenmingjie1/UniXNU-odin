"""Pin and save current public upstream display references; no device access."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/UniXNU-odin/research/github-display-20261104'
REPOS = (
    'UniXNU/GopFramebuffer', 'UniXNU/UniXNU',
    'oosexgang/hakios-xnu-kernel', 'oosexgang/hakios-metal',
    'OddlyLabs/unixnu-fuxi', 'Asultop/UniXNU-NX769J',
    'bangprovn/ios-fuxi', 'luuu20309/ios16_on_polaris_mix2s',
)


def fetch(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'MIX4-UniXNU-display-research',
        'Accept': 'application/vnd.github+json',
    })
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('Reference exceeded bounded download size')
    return data


def review(repo):
    folder = OUT / repo.replace('/', '--')
    folder.mkdir(parents=True, exist_ok=True)
    record = {'repository': repo, 'url': 'https://github.com/' + repo}
    try:
        for name, suffix in (('repository', ''), ('commits', '/commits?per_page=30')):
            data = fetch('https://api.github.com/repos/' + repo + suffix)
            (folder / (name + '.json')).write_bytes(data)
        commits = json.loads((folder / 'commits.json').read_bytes())
        revision = commits[0]['sha']
        record['revision'] = revision
        record['commit_url'] = record['url'] + '/tree/' + revision
        record['recent_commits'] = [
            {'sha': entry['sha'], 'subject': entry['commit']['message'].splitlines()[0]}
            for entry in commits
        ]
        # Kernel archives are very large; save their actual tree first, then
        # request selected blobs from the pinned revision when needed.
        if repo == 'oosexgang/hakios-xnu-kernel':
            data = fetch('https://api.github.com/repos/' + repo + '/git/trees/' + revision + '?recursive=1')
            (folder / 'tree.json').write_bytes(data)
            record['tree_truncated'] = json.loads(data).get('truncated')
        else:
            url = 'https://codeload.github.com/' + repo + '/tar.gz/' + revision
            data = fetch(url)
            (folder / 'source.tar.gz').write_bytes(data)
            record.update(archive_url=url, archive_sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                members = archive.getmembers()
                if sum(member.size for member in members) > 160 * 1024 * 1024:
                    raise ValueError('Reference exceeded bounded extraction size')
                archive.extractall(folder / 'source', filter='data')
            record['source'] = str(folder / 'source')
        record['status'] = 'fetched'
    except Exception as error:
        record.update(status='error', error=str(error))
    (folder / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(review, REPOS))
    (OUT / 'sources.json').write_text(json.dumps({
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Public GitHub source research only; no phone commands',
        'sources': records,
    }, indent=2) + '\n')
    for record in records:
        print(record['repository'], record['status'], record.get('revision'), record.get('error', ''))
