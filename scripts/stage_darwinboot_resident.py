"""Isolate the proven HakiOS resident handoff from the ordinary EBS loader."""
from pathlib import Path
import shutil

def stage_resident(staged):
    firmware=Path(__file__).resolve().parents[1]/'firmware'
    for name in ('OdinResident.h','OdinResident.c','OdinSecondary.S'):
        shutil.copy2(firmware/name,staged/name)
    path=staged/'DarwinBoot.c'
    source=path.read_text()
    source=source.replace('#include "WindowSize.h"','#include "WindowSize.h"\n#include "OdinResident.h"')
    start=source.index('  Status = GetMap (&Map, &Capacity, &MapSize, &Key, &Stride);',source.index('  Root->Close (Root); Root = NULL;'))
    end=source.index('\nFail:\n',start)
    source=source[:start]+'''  // The kernel window contains only pages reserved from conventional RAM.
  // Firmware, stack, USB buffers and loader images remain outside that window.
  // Success never returns and never runs the cleanup below; no EBS notification.
  Status = OdinResidentLaunch (ArgsAddress, Address + Kernel.Entry - Kernel.Base,
                               Address, Used, WindowSize, Kernel.Base);
  goto Fail;
'''+source[end:]
    assert 'gBS->ExitBootServices' not in source
    assert 'OdinResidentLaunch (ArgsAddress' in source
    path.write_text(source)
    return [staged/'OdinResident.c',staged/'OdinSecondary.S']
