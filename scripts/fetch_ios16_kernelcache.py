"""Fetch the pinned iOS16.5 kernelcache member with checked HTTP ranges/ZIP CRC."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import struct
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/UniXNU-odin/build/ios16-prelink'
DIRECTORY = json.loads((ROOT / 'work/ios-inputs/zip-directory.json').read_text())
MEMBER = next(m for m in DIRECTORY['members'] if m['name'] == 'kernelcache.release.iphone10b')


def fetch(start, count):
    req = urllib.request.Request(DIRECTORY['url'], headers={
        'Range': f'bytes={start}-{start+count-1}', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=40) as stream:
        expected = f"bytes {start}-{start+count-1}/{DIRECTORY['archive_bytes']}"
        if stream.status != 206 or stream.headers.get('Content-Range') != expected:
            raise ValueError('CDN did not return the exact requested archive range')
        blob = stream.read(count+1)
        if len(blob) != count:
            raise ValueError('Truncated or oversized HTTP range')
        return blob


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / MEMBER['name']
    receipt = target.with_suffix('.verified.json')
    if target.exists() and receipt.exists():
        saved = json.loads(receipt.read_text())
        if hashlib.sha256(target.read_bytes()).hexdigest() == saved['sha256']:
            print('Pinned kernelcache member already fetched and verified')
            return
    header = fetch(MEMBER['offset'], 30)
    assert header[:4] == b'PK\x03\x04'
    flags, method = struct.unpack_from('<HH', header, 6)
    assert method == MEMBER['method'] == 8 and not flags & 1
    nl, el = struct.unpack_from('<HH', header, 26)
    name = fetch(MEMBER['offset']+30, nl)
    assert name.decode() == MEMBER['name']
    start = MEMBER['offset'] + 30 + nl + el
    step = 1 << 20
    chunks = OUT / 'kernelcache.chunks'
    chunks.mkdir(exist_ok=True)

    def part(index):
        offset = index * step
        size = min(step, MEMBER['compressed']-offset)
        p = chunks / f'{index:03d}.bin'
        digest = p.with_suffix('.sha256')
        if not (p.exists() and digest.exists() and p.stat().st_size == size
                and hashlib.sha256(p.read_bytes()).hexdigest() == digest.read_text().strip()):
            blob = fetch(start+offset, size)
            p.write_bytes(blob)
            digest.write_text(hashlib.sha256(blob).hexdigest())
        print(f'chunk {index+1}/{(MEMBER["compressed"]+step-1)//step}', flush=True)
        return p.read_bytes()

    with ThreadPoolExecutor(max_workers=4) as pool:
        compressed = b''.join(pool.map(part, range((MEMBER['compressed']+step-1)//step)))
    inflater = zlib.decompressobj(-15)
    blob = inflater.decompress(compressed) + inflater.flush()
    assert inflater.eof and not inflater.unused_data
    assert len(blob) == MEMBER['bytes']
    assert f'{zlib.crc32(blob)&0xffffffff:08x}' == MEMBER['crc32']
    target.write_bytes(blob)
    record = {'url': DIRECTORY['url'], 'member': MEMBER, 'sha256': hashlib.sha256(blob).hexdigest(),
              'http_ranges_checked': True, 'zip_crc_verified': True, 'decompressed_macho_verified': False}
    receipt.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
