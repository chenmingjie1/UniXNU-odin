#!/usr/bin/env bash
# Run in the isolated Linux build root; no device access.
set -euo pipefail
cd /home/odin/unixnu-odin-build
export LD_LIBRARY_PATH="$PWD/packaging-tools/usr/lib/x86_64-linux-gnu"
export PATH="$PWD/packaging-tools/usr/bin:$PATH"
PAYLOAD_NAME=${PAYLOAD_NAME:-native-payload}
ESP_ARCHIVE=${ESP_ARCHIVE:-esp.tar.gz}
export FAT_MIB=${FAT_MIB:-32}
if [[ ! "$PAYLOAD_NAME" =~ ^(native-payload|prelinked-payload(-u[0-9]{2,4})?)$ ]]; then exit 2; fi
if [[ ! "$ESP_ARCHIVE" =~ ^esp(-u[0-9]{2,4})?\.tar\.gz$ ]]; then exit 2; fi
case "$FAT_MIB" in 32|64|96|128) ;; *) exit 2;; esac
mkdir -p "$PAYLOAD_NAME"
cd "$PAYLOAD_NAME"
tar -xzf "../$ESP_ARCHIVE"
mformat -i payload.fat -C -T "$((FAT_MIB*2048))" -v UNIXNUODIN ::
mcopy -i payload.fat -s esp/EFI ::/
mdir -i payload.fat -s ::/ > fat-directory.txt
mkdir -p readback
mcopy -i payload.fat -s ::/EFI readback/
python3 - <<'PY'
from pathlib import Path
import hashlib, json, struct, os
image=Path('payload.fat').read_bytes()
assert len(image)==int(os.environ['FAT_MIB'])*1024*1024 and image[510:512]==b'\x55\xaa'
bps=struct.unpack_from('<H',image,11)[0]
spc=image[13]; reserved=struct.unpack_from('<H',image,14)[0]
fats=image[16]; roots=struct.unpack_from('<H',image,17)[0]
sectors=struct.unpack_from('<H',image,19)[0] or struct.unpack_from('<I',image,32)[0]
spf=struct.unpack_from('<H',image,22)[0]
clusters=(sectors-reserved-fats*spf-(roots*32+bps-1)//bps)//spc
assert bps==512 and 4085<=clusters<65525
records=[]
for p in sorted(Path('esp').rglob('*')):
 if not p.is_file():continue
 rel=p.relative_to('esp'); b=p.read_bytes(); other=Path('readback')/rel
 assert b==other.read_bytes(),str(rel)
 records.append({'path':rel.as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
assert len(records)==4
Path('verification.json').write_text(json.dumps({'fat_type':'FAT16','bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'sectors_per_cluster':spc,'data_clusters':clusters,'all_payload_files_readback_equal':True,'files':records},indent=2)+'\n')
print('FAT16 readback passed:',len(records),'files,',len(image),'bytes')
PY
