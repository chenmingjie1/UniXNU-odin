"""Fetch only the pinned compiler-rt profile sources, checking Git blob IDs."""
from pathlib import Path
import base64, concurrent.futures, hashlib, json, os, urllib.request
ROOT=Path(__file__).resolve().parents[3]
REV=os.environ.get('ODIN_LLVM_PROFILE_REV','f28c006a5895fc0e329fe15fead81e37457cb1d1')
OUT=ROOT/('work/UniXNU-components/LLVM-profile-'+REV)
SOURCES={'InstrProfiling','InstrProfilingBuffer','InstrProfilingPlatformDarwin','InstrProfilingWriter','InstrProfilingInternal','InstrProfilingVersionVar'}
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MIX4-UniXNU-build'})
    with urllib.request.urlopen(req,timeout=40) as r:return r.read()
entries=[]
for folder in ('compiler-rt/lib/profile','compiler-rt/include/profile'):
    cache=OUT/(folder.replace('/','_')+'.json')
    cache.parent.mkdir(parents=True,exist_ok=True)
    if not cache.exists():cache.write_bytes(fetch('https://api.github.com/repos/llvm/llvm-project/contents/'+folder+'?ref='+REV))
    for e in json.loads(cache.read_text()):
        if e['type']=='file' and (e['name'].endswith(('.h','.inc')) or e['name'].removesuffix('.c') in SOURCES):entries.append(e)
def one(e):
    path=OUT/e['path'];path.parent.mkdir(parents=True,exist_ok=True)
    data=path.read_bytes() if path.exists() else base64.b64decode(json.loads(fetch(e['git_url']))['content'])
    sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if sha!=e['sha']:raise RuntimeError('Blob mismatch '+e['path'])
    path.write_bytes(data)
    print(e['path'],len(data),flush=True)
    return {'path':e['path'],'git_blob':sha,'sha256':hashlib.sha256(data).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(one,entries))
(OUT/'source-receipt.json').write_text(json.dumps({'repository':'https://github.com/llvm/llvm-project','revision':REV,'files':records},indent=2)+'\n')
