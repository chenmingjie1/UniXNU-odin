"""Archive the actual u65 screen; distinguish executed checkpoints from hangs."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/MIX4-UniXNU-desktop-u65'
photo = ROOT / 'outputs/mobile-inbox/received/files/50804d626c878c3dd8591d552ce1e625.jpg'
assert hashlib.sha256(photo.read_bytes()).hexdigest() == 'ad562d9fdea4f159a238eabe23aad74d7c858dbf121c7a837fe7ee54583aebce'
p = OUT / 'device-outcome.json'
result = json.loads(p.read_text())
result.update(exit_boot_services_confirmed=True, xnu_execution_confirmed=True,
    physical_desktop_confirmed=False,
    physical_screen_observation='16 entry markers and A000-A007 register rows; residual firmware menu underneath',
    screen_evidence=str(photo), screen_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(),
    last_confirmed_source_checkpoint='odin_c_platform, immediately before PE_init_platform(FALSE,args)',
    pe_init_platform_hang_proven=False,
    registers={'A000':'00000000412FD050','A001':'0000000000101122',
        'A002':'0000000010212122','A003':'00000022A51A251A',
        'A004':'0000000030D00808','A005':'00000000EFF76000',
        'A006':'00000000EFF77000','A007':'0C88044F00BB44FF'},
    next='Add bounded continuous early-platform checkpoints and KVA exception capture before VM takeover')
p.write_text(json.dumps(result, indent=2)+'\n')
print('u65 physical XNU entry confirmed; desktop still unconfirmed')
