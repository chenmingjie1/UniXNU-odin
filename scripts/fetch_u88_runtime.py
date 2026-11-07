"""Download, verify, and assemble the fixed u88 runtime (Python 3.11+)."""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import shutil
import sys
import urllib.request
import zipfile

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def safe_path(root,name):
    if not isinstance(name,str) or '\\' in name or ':' in name or Path(name).is_absolute():
        raise ValueError('Invalid package path')
    target=(root/name).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Path escapes output directory')
    return target

def download(base,row,cache):
    name=row['name']
    if Path(name).name!=name:raise ValueError('Asset name is not a filename')
    target=cache/name
    if target.exists():
        if target.stat().st_size==row['bytes'] and sha(target)==row['sha256']:return target
        raise ValueError('Existing download differs from release: '+str(target))
    partial=cache/(name+'.download')
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>row['bytes']:raise ValueError('Oversized partial download: '+str(partial))
    if offset<row['bytes']:
        headers={'User-Agent':'UniXNU-u88-runtime','Accept-Encoding':'identity'}
        if offset:headers['Range']='bytes='+str(offset)+'-'
        request=urllib.request.Request(base+'/'+name,headers=headers)
        with urllib.request.urlopen(request,timeout=90) as response:
            if offset and (response.status!=206 or not response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-')):
                raise ValueError('Server did not honor the requested download resume range')
            if not offset and response.status!=200:raise ValueError('Unexpected download status')
            with partial.open('ab' if offset else 'wb') as stream:
                while chunk:=response.read(1<<20):
                    offset+=len(chunk)
                    if offset>row['bytes']:raise ValueError('Oversized release download')
                    stream.write(chunk)
    if partial.stat().st_size!=row['bytes'] or sha(partial)!=row['sha256']:
        raise ValueError('Release SHA256 mismatch: '+name)
    partial.replace(target)
    print('Downloaded and verified:',name,flush=True)
    return target

class PartReader(io.RawIOBase):
    def __init__(self,paths):
        self.paths=iter(paths);self.current=None
    def readable(self):return True
    def readinto(self,buffer):
        while True:
            if self.current is None:
                path=next(self.paths,None)
                if path is None:return 0
                self.current=path.open('rb')
            count=self.current.readinto(buffer)
            if count:return count
            self.current.close();self.current=None
    def close(self):
        if self.current:self.current.close()
        super().close()

def unpack_media(media,parts,root):
    output=safe_path(root,media['target'])
    if output.exists():
        if output.stat().st_size==media['raw_bytes'] and sha(output)==media['raw_sha256']:
            print('Media already verified:',output.name,flush=True);return
        raise ValueError('Existing runtime media differs; choose an empty output directory: '+str(output))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.name+'.unpacking')
    digest=hashlib.sha256();count=0
    with PartReader(parts) as joined,io.BufferedReader(joined) as buffered,gzip.GzipFile(fileobj=buffered,mode='rb') as source,temporary.open('wb') as target:
        while chunk:=source.read(8<<20):
            count+=len(chunk)
            if count>media['raw_bytes']:raise ValueError('Oversized unpacked media')
            target.write(chunk);digest.update(chunk)
    if count!=media['raw_bytes'] or digest.hexdigest()!=media['raw_sha256']:
        raise ValueError('Unpacked media SHA256 mismatch: '+media['kind'])
    temporary.replace(output)
    print('Assembled and verified:',output.name,flush=True)

def unpack_core(path,root):
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            dest=safe_path(root,item.filename)
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlinks are not supported')
            data=archive.read(item)
            if dest.exists():
                if dest.read_bytes()!=data:raise ValueError('Refusing to overwrite different file: '+str(dest))
            else:
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('u88-runtime'))
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--offline',action='store_true',help='Use already downloaded, verified files only')
    args=parser.parse_args()
    script=Path(__file__).resolve()
    candidates=(script.parent/'u88-downloads.json',script.parents[1]/'configs/runtime/u88-downloads.json')
    index_path=next((p for p in candidates if p.is_file()),None)
    if index_path is None:raise ValueError('Missing u88-downloads.json; use the launcher zip or repository checkout')
    index=json.loads(index_path.read_text(encoding='utf-8'))
    root=args.output.resolve();cache=(args.cache or root/'downloads').resolve()
    root.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
    def get(row):
        if args.offline:
            path=cache/row['name']
            if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('Offline asset differs: '+str(path))
            return path
        return download(index['download_base'],row,cache)
    unpack_core(get(index['core']),root)
    for media in index['media']:
        unpack_media(media,[get(row) for row in media['parts']],root)
    import subprocess
    subprocess.run([sys.executable,str(root/'scripts/boot_u88_runtime.py'),'--runtime',str(root),'--verify-only'],check=True)
    print('u88 runtime is complete. Follow README.zh-CN.md to start your MIX 4.',flush=True)

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as error:
        print('STOP:',error,file=sys.stderr);sys.exit(1)
