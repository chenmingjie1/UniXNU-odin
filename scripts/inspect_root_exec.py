"""Extract and audit critical Mach-O files from the local copied APFS root."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'work/hakios-upstream/tools/apfs'))
import apfs

class BinaryImage:
    def __init__(self, path):
        self.stream = open(path, 'rb')
        self.path = path
        self.size = Path(path).stat().st_size
    def read(self, offset, length):
        self.stream.seek(offset)
        return self.stream.read(length)
    def close(self):
        self.stream.close()

apfs.RawImage = BinaryImage
def audit_slice(data, file_offset=0):
    assert data[:4] == bytes.fromhex('cffaedfe')
    cpu, subtype, filetype, ncmds, command_bytes, flags = struct.unpack_from('<6I', data, 4)
    assert cpu == 0x100000c and 32+command_bytes <= len(data)
    directories, commands = [], []
    offset = 32
    for index in range(ncmds):
        command, size = struct.unpack_from('<II', data, offset)
        assert size >= 8 and offset+size <= 32+command_bytes
        row = {'command': hex(command), 'size': size, 'slice_offset': file_offset}
        if command in (0xc, 0xd, 0xe, 0x80000018, 0x8000001c):
            string_offset, = struct.unpack_from('<I', data, offset+8)
            row['name'] = data[offset+string_offset:offset+size].split(b'\0')[0].decode(errors='replace')
        if command == 0x1d:
            start, length = struct.unpack_from('<II', data, offset+8)
            assert start+length<=len(data)
            row.update(offset=start, bytes=length)
            magic, total, count = struct.unpack_from('>III', data, start)
            assert magic == 0xfade0cc0 and total<=length and 12+count*8<=total
            for slot in range(count):
                kind, relative = struct.unpack_from('>II', data, start+12+8*slot)
                assert relative+8<=total
                position = start+relative
                blob_magic, blob_size = struct.unpack_from('>II', data, position)
                assert relative+blob_size<=total
                if blob_magic != 0xfade0c02:
                    continue
                blob = data[position:position+blob_size]
                version, cdflags, hash_offset, identifier_offset, special, codes, limit = struct.unpack_from('>7I', blob, 8)
                hash_size, hash_type, platform, page_shift = struct.unpack_from('>4B', blob, 36)
                algorithms = {1:'sha1', 2:'sha256', 3:'sha256', 4:'sha384'}
                algorithm = algorithms[hash_type]
                page = 1<<page_shift
                assert limit<=len(data) and codes==(limit+page-1)//page
                assert hash_offset+codes*hash_size<=len(blob) and identifier_offset<len(blob)
                bad = []
                for entry in range(codes):
                    expected = blob[hash_offset+entry*hash_size:hash_offset+(entry+1)*hash_size]
                    actual = hashlib.new(algorithm, data[entry*page:min((entry+1)*page,limit)]).digest()[:hash_size]
                    if expected != actual:
                        bad.append(entry)
                directories.append({'slot_type': kind, 'version': hex(version),
                    'flags': hex(cdflags), 'hash_type': hash_type, 'hash_size':hash_size,
                    'code_limit':limit, 'code_slots':codes, 'page_shift':page_shift,
                    'slice_offset':file_offset, 'cpu_subtype':subtype,
                    'identifier':blob[identifier_offset:].split(b'\0')[0].decode(errors='replace'),
                    'cdhash':hashlib.new(algorithm,blob).digest()[:20].hex(),
                    'page_hash_mismatches':bad})
            assert directories, 'Signed Mach-O must contain a CodeDirectory'
        commands.append(row)
        offset += size
    assert offset==32+command_bytes
    return dict(cpu=cpu,cpu_subtype=subtype,filetype=filetype,flags=flags,
                code_directories=directories,load_commands=commands)

def audit_file(data, name):
    report = {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'magic': data[:4].hex(), 'code_directories': [], 'load_commands': []}
    if data[:4] == bytes.fromhex('cffaedfe'):
        report.update(audit_slice(data))
    else:
        # Original arm64/arm64e universal migrators use slice-relative signature
        # offsets and page hashes. Preserve/hash the complete file for trust
        # identity, but verify every architecture's CodeDirectory separately.
        assert data[:4] == bytes.fromhex('cafebabe'), name
        count = struct.unpack_from('>I',data,4)[0]
        assert 0<count<=16 and 8+20*count<=len(data)
        report['slices']=[]
        extents=[]
        for index in range(count):
            cpu,subtype,start,length,alignment=struct.unpack_from('>5I',data,8+20*index)
            assert cpu==0x100000c and alignment<32 and start%(1<<alignment)==0
            assert start>=8+20*count and start+length<=len(data)
            assert all(start+length<=lo or hi<=start for lo,hi in extents)
            extents.append((start,start+length))
            part=audit_slice(data[start:start+length],start)
            assert (part['cpu'],part['cpu_subtype'])==(cpu,subtype)
            report['slices'].append(dict(offset=start,bytes=length,cpu=cpu,cpu_subtype=subtype))
            report['code_directories']+=part['code_directories']
            report['load_commands']+=part['load_commands']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--path', action='append', dest='paths',
                        help='Audit this absolute root path; repeat for several files.')
    parser.add_argument('--paths-file',type=Path,help='JSON list of exact absolute root paths')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    volume = apfs.pick_volume(apfs.Container(args.image), None)
    reports = []
    if args.paths_file:
        assert not args.paths
        args.paths=json.loads(args.paths_file.read_text())
        assert isinstance(args.paths,list) and args.paths and len(args.paths)==len(set(args.paths))
        assert all(isinstance(p,str) and p.startswith('/') and '..' not in p.split('/') for p in args.paths)

    for name in args.paths or ['/sbin/launchd', '/usr/lib/dyld', '/usr/libexec/backboardd',
                              '/System/Library/CoreServices/SpringBoard.app/SpringBoard']:
        hit = volume.lookup(name)
        data = volume.inode(hit[0]).contents()
        target = args.output_dir/name.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == data
        else:
            target.write_bytes(data)
        reports.append(audit_file(data, name))
    (args.output_dir/'verification.json').write_text(json.dumps(reports,indent=2)+'\n')
    for report in reports:
        print(report['path'], report['bytes'], json.dumps(report['code_directories']))


if __name__ == '__main__':
    main()
