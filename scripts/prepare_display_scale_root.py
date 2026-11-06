"""Set an explicit logical UI scale through the exact QuartzCore environment API.

This copies only a computer APFS fixture. Two launch job plists change; every
other stored payload, compressed fork, permission and owner is checked intact.
No executable, signature, physical density or hardware identity is changed.
"""
from pathlib import Path
import argparse,hashlib,json,plistlib,stat
import prepare_launch_services_root as base

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path)
p.add_argument('target',type=Path)
p.add_argument('--scale',type=int,choices=(1,2,3),default=3)
a=p.parse_args()
assert a.source.resolve()!=a.target.resolve() and not a.target.exists()
stage=a.target.with_suffix('.staging');stage.mkdir(exist_ok=False)
container=base.apfs.Container(a.source);v=base.apfs.pick_volume(container,None)
jobs={'/redwood/LaunchDaemons/'+s+'.plist' for s in ('com.apple.SpringBoard','com.apple.backboardd')}
changed=[]

def clone(oid,name='',path=''):
    inode=v.inode(oid)
    node=base.mkapfs.Node(name,inode.mode,target=inode.symlink_target_bytes() if inode.is_link else None)
    node.uid,node.gid=inode.owner,inode.group
    if inode.is_reg:
        if path in jobs:
            before=inode.contents();job=plistlib.loads(before)
            old=dict(job.get('EnvironmentVariables',{}))
            assert 'CA_MAIN_DISPLAY_SCALE' not in old
            job.setdefault('EnvironmentVariables',{})['CA_MAIN_DISPLAY_SCALE']=str(a.scale)
            out=stage/name;out.write_bytes(plistlib.dumps(job,fmt=plistlib.FMT_BINARY))
            node.source=str(out)
            changed.append(dict(path=path,label=job['Label'],source_sha256=hashlib.sha256(before).hexdigest(),
                output_sha256=base.digest(out),environment_before=old,
                change={'CA_MAIN_DISPLAY_SCALE':str(a.scale)}))
        else:node.original_inode=inode
    elif inode.is_dir:
        for child,child_oid,_ in v.dir_entries(oid):node.children[child]=clone(child_oid,child,path+'/'+child)
    else:assert inode.is_link,(path,inode.mode)
    return node

tree=clone(2)
assert len(changed)==2
raw=a.target.with_suffix('.unrepaired.apfs')
assert not raw.exists() and not a.target.with_suffix('.spool').exists()
with a.target.with_suffix('.spool').open('w+b') as spool:
    copied=base.CloneVolume(0,'UniXNUHostSystem',tree,True,1683900000000000000,spool,[])
    writer=base.mkapfs.Container([copied],256,'UniXNUHostScale-u18')
    writer.layout();writer.write(str(raw))
base.repair(raw,a.target)
print('Logical-scale root written; checking original payloads',flush=True)
check_container=base.apfs.Container(a.target);check=base.apfs.pick_volume(check_container,None)
paths=base.index_paths(check);count=0

def verify(node,path=''):
    global count
    if hasattr(node,'original_inode'):
        old=node.original_inode;new=check.inode(paths[path][0])
        kind,data=base.stored_payload(new);old_kind,old_data=base.stored_payload(old)
        assert new.size==old.size and kind==old_kind and new.decmpfs==old.decmpfs,path
        assert hashlib.sha256(data).digest()==hashlib.sha256(old_data).digest(),path
        assert (new.mode,new.owner,new.group)==(old.mode,old.owner,old.group),path
        count+=1
    for name,child in node.children.items():verify(child,path+'/'+name)

verify(tree)
for row in changed:
    data=check.inode(paths[row['path']][0]).contents()
    assert hashlib.sha256(data).hexdigest()==row['output_sha256']
    job=plistlib.loads(data)
    assert job['EnvironmentVariables']==dict(row['environment_before'],CA_MAIN_DISPLAY_SCALE=str(a.scale))
record=dict(scope='Computer-only explicit logical UI scale; not a physical density measurement',
    source=str(a.source),source_sha256=base.digest(a.source),output=str(a.target),sha256=base.digest(a.target),
    bytes=a.target.stat().st_size,scale=a.scale,logical_size=[1080/a.scale,2400/a.scale],changes=changed,
    existing_file_payloads_preserved=count,all_other_stored_payloads_verified=True,
    executables_modified=False,desktop_verified=False,device_commands_executed=False,
    contract='Exact QuartzCore CA_MAIN_DISPLAY_SCALE getenv/atof/positive check and first-display scale setter at 0x1884e29a0..0x1884e29e4')
a.target.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
check_container.close();container.close();print(json.dumps(record,indent=2))
