import gzip
import importlib.util
import io
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

STAGE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
boot=module('boot',STAGE/'scripts/boot_u88_runtime.py')
fetch=module('fetch',STAGE/'scripts/fetch_u88_runtime.py')

class RuntimeTests(unittest.TestCase):
    def test_response_crc_bounds_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'file';p.write_bytes(bytes(range(256))*4)
            files={5:{'absolute':p,'bytes':p.stat().st_size,'mtime':p.stat().st_mtime_ns,'path':'file'}}
            raw=boot.response(files,5,253,11,17)
            self.assertEqual(struct.unpack('<8sIIQII',raw[:32]),(b'ODNRD001',17,5,253,11,zlib.crc32(raw[32:])&0xffffffff))
            self.assertEqual(raw[32:],p.read_bytes()[253:264])
            for args in ((6,0,1),(5,1024,1),(5,-1,1),(5,0,0),(5,0,1048577)):
                with self.assertRaises(ValueError):boot.response(files,*args,18)
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):boot.response(files,5,0,1,18)

    def test_transport_and_idle_assertion_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'payload';p.write_bytes(b'test payload')
            files={5:{'absolute':p,'bytes':12,'mtime':p.stat().st_mtime_ns,'path':'payload'}}
            class Device:
                def __init__(self):self.calls=[];self.reads=iter(('odin-read: 00000001:00000005:0000000000000002:00000004','idle:desktop-ready','idle:kernel-core7'))
                def devices(self):return ['odin-unixnu-u64']
                def run(self,*args,**kwargs):
                    self.calls.append(args)
                    if args[-1]=='odin-read':return 0,next(self.reads)
                    if args[-1]=='kernel-postvm':return 0,'stage=4e'
                    if args[-2]=='stage':
                        self.frame=Path(args[-1]).read_bytes()
                    return 0,'OK'
            device=Device()
            boot.serve(device,{'remote_serial':'odin-unixnu-u64'},files,root,120,root/'events.jsonl')
            self.assertEqual(device.frame[32:],b'st p')
            commands=[c[-1] for c in device.calls]
            self.assertLess(commands.index('kernel-postvm'),commands.index('ui-wake'))
            self.assertLess(commands.index('desktop'),commands.index('ui-wake'))

    def test_media_reassembly_across_small_parts_and_hash_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=bytes(range(256))*5000;compressed=gzip.compress(data,mtime=0)
            parts=[]
            for i in range(0,len(compressed),37):
                p=root/str(i);p.write_bytes(compressed[i:i+37]);parts.append(p)
            import hashlib
            media={'target':'payload/system','kind':'system','raw_bytes':len(data),'raw_sha256':hashlib.sha256(data).hexdigest()}
            fetch.unpack_media(media,parts,root)
            self.assertEqual((root/'payload/system').read_bytes(),data)
            media['target']='bad';media['raw_sha256']='0'*64
            with self.assertRaises(ValueError):fetch.unpack_media(media,parts,root)

    def test_path_escape_rejected(self):
        for name in ('../outside','/absolute','C:/absolute','a/../../outside','..\\outside'):
            for resolver in (boot.resolve_file,fetch.safe_path):
                with self.assertRaises(ValueError):resolver(Path.cwd(),name)

if __name__=='__main__':unittest.main(verbosity=2)
