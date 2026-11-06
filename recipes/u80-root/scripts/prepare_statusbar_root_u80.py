"""Replace only the existing signed SpringBoard UI library in a new APFS file."""
from pathlib import Path
import hashlib,json,struct
from prepare_launch_services_root import apfs,mkapfs,CloneVolume,index_paths,stored_payload,digest
from repair_mkapfs_spaceman import repair

D=Path(__file__).resolve().parents[1]
source=D/'build/root-media/system-host-input-u59.apfs'
out=D/'build/root-media/system-host-input-u80.apfs'
tool=D/'build/host-virtual-input-u80/host_swipe'
target='/redwood/host-input/libodin-ui-unlock.dylib'
assert not out.exists()
audit=json.loads((tool.parent/'tool-audit.json').read_text())[0]
assert digest(tool)==audit['sha256'] and audit['filetype']==6
assert audit['code_directories'] and all(not d['page_hash_mismatches'] for d in audit['code_directories'])
c=apfs.Container(source);v=apfs.pick_volume(c,None);before=index_paths(v)
replaced=[]
def clone(oid,name='',path=''):
    inode=v.inode(oid)
    node=mkapfs.Node(name,inode.mode,target=inode.symlink_target_bytes() if inode.is_link else None)
    node.uid,node.gid=inode.owner,inode.group
    if inode.is_reg:
        if path==target:
            node.source=str(tool);replaced.append(path)
        else:node.original_inode=inode
    elif inode.is_dir:
        for child,child_oid,_ in v.dir_entries(oid):node.children[child]=clone(child_oid,child,path+'/'+child)
    else:assert inode.is_link
    return node
tree=clone(2);assert replaced==[target]
with out.with_suffix('.spool').open('w+b') as spool:
    volume=CloneVolume(0,'UniXNUHostSystem',tree,True,1683900000000000000,spool,[])
    writer=mkapfs.Container([volume],256,'UniXNUOdinStatusBar-u80');writer.layout()
    raw=out.with_suffix('.unrepaired.apfs');writer.write(str(raw))
repair(raw,out)
cc=apfs.Container(out);cv=apfs.pick_volume(cc,None);after=index_paths(cv)
assert before.keys()==after.keys()
for path,expected in volume.preserved.items():
    inode=cv.inode(after['/'+path][0]);kind,payload=stored_payload(inode)
    assert inode.size==expected['bytes'] and kind==expected['kind']
    assert hashlib.sha256(payload).hexdigest()==expected['stored_sha256'],path
    assert (inode.decmpfs.hex() if inode.decmpfs else None)==expected['decmpfs'],path
assert hashlib.sha256(cv.inode(after[target][0]).contents()).hexdigest()==digest(tool)
cc.close();c.close()
base_trust=D/'build/root-media/host-input-development-trust-u59.bundle'
trust=base_trust.read_bytes()
assert digest(base_trust)==json.loads(source.with_suffix('.json').read_text())['trust_sha256']
assert struct.unpack_from('<2I',trust)==(1,8)
version,_,count=struct.unpack_from('<I16sI',trust,8)
assert version==2 and len(trust)==32+count*24
entries={trust[i:i+24] for i in range(32,len(trust),24)}
for cd in audit['code_directories']:
    entries.add(bytes.fromhex(cd['cdhash'])+struct.pack('<4B',cd['hash_type'],0,0,0))
ordered=b''.join(sorted(entries));identifier=hashlib.sha256(b'UniXNU.Odin.StatusBar.u80\0'+ordered).digest()[:16]
trust_out=D/'build/root-media/host-input-development-trust-u80.bundle'
assert not trust_out.exists();trust_out.write_bytes(struct.pack('<3I16sI',1,8,2,identifier,len(entries))+ordered)
record=dict(source=str(source),source_sha256=digest(source),output=str(out),sha256=digest(out),bytes=out.stat().st_size,
    replaced_paths=replaced,all_other_stored_payloads_verified=True,preserved_files=len(volume.preserved),
    launch_jobs_unchanged=True,tool_sha256=digest(tool),trust_output=str(trust_out),trust_sha256=digest(trust_out),
    library_selected_by_existing_kernel_exec_policy=True,desktop_verified=False,device_commands_executed=False)
out.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
