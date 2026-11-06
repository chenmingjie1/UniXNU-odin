#!/usr/bin/env python3
"""Resolve actual Linux cross tools for the separate UniXNU build."""
import os,sys
from pathlib import Path
args=sys.argv[1:]
sdk='/home/odin/xnu-work/project/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'
find=False
while args and args[0].startswith('-'):
    flag=args.pop(0)
    if flag in ('-sdk','--sdk'):args.pop(0)
    elif flag in ('--show-sdk-path','-show-sdk-path'):print(sdk);sys.exit(0)
    elif flag in ('-find','--find','-f'):find=True;break
    else:raise SystemExit('Unsupported explicit tool query: '+flag)
name=args.pop(0)
tools={'clang':'/usr/bin/clang','clang++':'/usr/bin/clang++','ar':'/usr/bin/llvm-ar',
       'nm':'/home/odin/xnu-work/theos/toolchain/linux/iphone/bin/nm',
       'libtool':'/home/odin/xnu-work/theos/toolchain/linux/iphone/bin/libtool'}
path=tools.get(name)
if not path:raise SystemExit('Tool not qualified in this offline adapter: '+name)
if find:print(path);sys.exit(0)
if name=='ar':args=['--format=darwin',*args]
os.execv(path,[path,*args])
