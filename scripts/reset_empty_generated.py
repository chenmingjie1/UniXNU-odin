from pathlib import Path
import json
root=Path('/home/odin/unixnu-odin-build')
obj=root/'upstream/build/xnu/ios-obj'
removed=[]
for name in ('bsd.syscalls.master','syscall.h','sysproto.h','init_sysent.c','syscalls.c','audit_kevents.c','systrace_args.c'):
    for p in obj.rglob(name):
        # Reset only this target's generated source, never the immutable import.
        p.unlink()
        removed.append(str(p.relative_to(obj)))
(root/'evidence/generated-files-reset.json').write_text(json.dumps(removed,indent=2)+'\n')
print('Reset',len(removed),'generated syscall outputs after fixing XCRUN resolution')
