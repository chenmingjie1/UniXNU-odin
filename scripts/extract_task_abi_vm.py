"""Read actual build DWARF for a bounded, read-only host task snapshot."""
from pathlib import Path
import hashlib,json,re,subprocess

base=Path('/home/odin/unixnu-odin-build')
obj=base/'upstream/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
out=base/'evidence/host-task-abi-u28';out.mkdir(parents=True,exist_ok=True)
specs=[('proc','bsd/DEVELOPMENT/kern_proc.o',('p_list','p_pid','p_comm','p_proc_ro')),
       ('proc_ro','bsd/DEVELOPMENT/kern_proc.o',('pr_task',)),
       ('task','osfmk/DEVELOPMENT/task.o',('threads','thread_count','bsd_info')),
       ('thread','osfmk/DEVELOPMENT/thread.o',('task_threads','task','kernel_stack','continuation','wait_event','state','machine','thread_id')),
       ('machine_thread','osfmk/DEVELOPMENT/thread.o',('upcb','kstackptr','CpuDatap','uregs')),
       ('arm_saved_state64','osfmk/DEVELOPMENT/thread.o',('x','fp','lr','sp','pc','cpsr'))]
results={}
for name,relative,wanted in specs:
    path=obj/relative
    raw=subprocess.run(['llvm-dwarfdump','--name='+name,'--show-children',str(path)],check=True,capture_output=True,text=True).stdout
    (out/(name+'.dwarf.txt')).write_text(raw)
    nodes=re.split(r'(?=^0x[0-9a-f]+:)',raw,flags=re.M)
    fields={}
    for node in nodes:
        header=node.splitlines()[0] if node.splitlines() else ''
        # Only direct members of a top-level matched structure, not nested types.
        if not re.match(r'0x[0-9a-f]+:   DW_TAG_member$',header):continue
        key=re.search(r'DW_AT_name\s+\("([^"]+)"\)',node)
        offset=re.search(r'DW_AT_data_member_location\s+\((0x[0-9a-f]+)\)',node)
        if key and offset and key[1] in wanted:
            value=int(offset[1],16)
            assert key[1] not in fields or fields[key[1]]==value
            fields[key[1]]=value
    results[name]=dict(object=relative,object_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       fields=fields,missing=sorted(set(wanted)-set(fields)))
(out/'task-abi.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
