#!/usr/bin/env python3
"""Restore executable script bits lost by the Windows archive extraction.

Only the separate working source changes. The source receipt and reference
tree remain immutable; permissions and later Linux edits are recorded.
"""
from pathlib import Path
import json
ROOT=Path('/home/odin/unixnu-odin-build')
tree=ROOT/'upstream/.cache/xnu-work'
changed=[]
for p in tree.rglob('*'):
    if not p.is_file(): continue
    with p.open('rb') as f: prefix=f.read(2)
    if prefix == b'#!':
        p.chmod(p.stat().st_mode | 0o111)
        changed.append(str(p.relative_to(tree)))
(ROOT/'evidence/restored-script-modes.json').write_text(json.dumps(changed,indent=2)+'\n')
doconf=tree/'SETUP/config/doconf'
text=doconf.read_text()
if text.startswith('#!/bin/csh -f\n'):
    doconf.write_text(text.replace('#!/bin/csh -f\n','#!/usr/bin/env -S tcsh -f\n',1))
# This one UUID is statically a 16-byte data buffer. Use the explicit bytes
# constructor, preserving the copy and length without pretending upstream
# clang implements Apple's type-layout builtins.
user=tree/'iokit/Kernel/IOUserServer.cpp'
text=user.read_text()
text=text.replace('OSData::withValue(p_uuid)', 'OSData::withBytes(p_uuid, sizeof(p_uuid))')
user.write_text(text)
pm=tree/'iokit/Kernel/IOPMrootDomain.cpp'
text=pm.read_text()
for before,after in {
    'aggressivesData->appendValue(newRecord)': 'aggressivesData->appendBytes(&newRecord, sizeof(newRecord))',
    'OSData::withValue(*calendar)': 'OSData::withBytes(calendar, sizeof(*calendar))',
    'OSData::withValue(gPMStats)': 'OSData::withBytes(&gPMStats, sizeof(gPMStats))',
    'OSData::withValue(flags)': 'OSData::withBytes(&flags, sizeof(flags))',
}.items():text=text.replace(before,after)
pm.write_text(text)
for filename,before,after in [
    ('iokit/Kernel/IOPolledInterface.cpp','ctx->extents->appendValue(extent)','ctx->extents->appendBytes(&extent, sizeof(extent))'),
    ('libkern/c++/OSSerializeBinary.cpp','indexData->appendValue(offset)','indexData->appendBytes(&offset, sizeof(offset))'),
    ('iokit/Kernel/arm/AppleARMSMP.cpp','OSData::withValue(topology_info->cpus[cpu_id].phys_id)','OSData::withBytes(&topology_info->cpus[cpu_id].phys_id, sizeof(topology_info->cpus[cpu_id].phys_id))'),
    ('iokit/Kernel/IOCPU.cpp','OSData::withValue(tmpLong)','OSData::withBytes(&tmpLong, sizeof(tmpLong))'),
    ('iokit/Kernel/IOInterruptController.cpp','OSData::withValue(vectorNumber)','OSData::withBytes(&vectorNumber, sizeof(vectorNumber))'),
    ('iokit/Kernel/PassthruInterruptController.cpp','OSData::withValue(zero)','OSData::withBytes(&zero, sizeof(zero))'),
    ('iokit/Kernel/IOKitDebug.cpp','data->appendValue(instFlags)','data->appendBytes(&instFlags, sizeof(instFlags))'),
    ('libkern/c++/OSKext.cpp','OSData::withValue(uuid_cmd->uuid)','OSData::withBytes(uuid_cmd->uuid, sizeof(uuid_cmd->uuid))'),
    ('libkern/c++/OSKext.cpp','OSData::withValue(*header)','OSData::withBytes(header, sizeof(*header))'),
]:
    p=tree/filename
    s=p.read_text()
    if before in s:p.write_text(s.replace(before,after))
print('Restored executable bits on',len(changed),'scripts')
