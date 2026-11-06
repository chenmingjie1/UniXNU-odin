"""Disassemble exact local shared-cache exported code without a Mac."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/MIX4-odin-porting/source'))
from symbolicate_ios_stacks import Cache,DEFAULT
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--image',required=True)
p.add_argument('--symbol',action='append',default=[])
p.add_argument('--address',action='append',type=lambda value:int(value,0),default=[])
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
c=Cache(DEFAULT);im=next(i for i in c.images if i.name.endswith(a.image));symbols=im.symbols()
assert a.symbol or a.address
tools=ROOT/'work/toolchains/llvm-mingw/llvm-mingw-20240619-ucrt-x86_64/bin'
records=[]
selected=[]
for name in a.symbol:
    matches=[(address,n) for address,n in symbols if n==name];assert len(matches)==1
    selected.append((matches[0][0],name))
for address in a.address:
    assert any(at==address for at,_ in symbols),'Address must be an actual local function boundary'
    selected.append((address,'function_'+hex(address)))
for start,name in selected:
    end=min(address for address,_ in symbols if address>start)
    assert 0<end-start<=65536 and (end-start)%4==0
    raw=c.read(start,end-start);stem=name.lstrip('_')
    source=a.output/(stem+'.S');obj=a.output/(stem+'.o')
    source.write_text('.text\n.globl inspected_cache_code\ninspected_cache_code:\n'+
        ''.join(f'.inst 0x{word:08x}\n' for word, in struct.iter_unpack('<I',raw)))
    subprocess.run([str(tools/'clang.exe'),'--target=aarch64-none-elf','-c',str(source),'-o',str(obj)],check=True)
    text=subprocess.run([str(tools/'llvm-objdump.exe'),'-d','--adjust-vma='+hex(start),str(obj)],
                        check=True,capture_output=True,text=True).stdout
    (a.output/(stem+'.txt')).write_text(text)
    records.append(dict(symbol=name,address=hex(start),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
c.close()
(a.output/'qualification-inputs.json').write_text(json.dumps(dict(image=im.name,symbols=records),indent=2)+'\n')
print(json.dumps(records,indent=2))
