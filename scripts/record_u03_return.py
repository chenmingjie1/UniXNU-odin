"""Record observed return to Android without inferring who restarted it."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re

ROOT = Path(__file__).resolve().parents[3]
RELEASE = ROOT / 'outputs/MIX4-UniXNU-core-u03'
RUN = RELEASE / 'runs/20261103-072201'
baseline = json.loads((ROOT / 'outputs/MIX4-iOS16.5-system-r16-source-kernel/manifest.json').read_text(encoding='utf-8'))['partition_baseline']['partitions']
observed = {name: digest for digest, name in re.findall(r'([0-9a-f]{64})\s+/dev/block/by-name/(\w+)', (RUN / 'partition-postflight.txt').read_text())}
assert len(observed) == len(baseline) == 14
assert all(observed[item['name']] == item['sha256'] for item in baseline)
now = datetime.now(timezone(timedelta(hours=8))).isoformat()
outcome = json.loads((RELEASE / 'device-outcome.json').read_text(encoding='utf-8'))
outcome.update(updated_at=now, physical_screen_observation='User reported 关机页面; exact UI and manual restart not yet clarified',
               android_return_confirmed=True, android_boot_completed=True,
               android_return_boot_id='7725696d-7985-4816-b0f1-47004aeeb598',
               restart_actor='unknown; clarification pending',
               adb_after_boot=['9bd99408 device product:odin model:2106118C device:odin'],
               postboot_partition_hashes_checked=True, postboot_partition_hashes_matching=14,
               kernel_execution_confirmed=False, physical_panel_confirmed=False)
for path in [RELEASE / 'device-outcome.json', RUN / 'device-outcome.json']:
    path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for path in [ROOT / 'work/UniXNU-odin/migration-status.json', ROOT / 'outputs/MIX4-odin-porting/暂停与继续状态.json']:
    status = json.loads(path.read_text(encoding='utf-8'))
    status.update(updated_at=now, current_device_state='Android ADB returned, sys.boot_completed=1; u03 XNU execution unconfirmed',
                  latest_device_outcome=str(RELEASE / 'device-outcome.json'))
    if 'phase' in status:
        status['phase']='u03 returned to Android; preparing retained BDS handoff diagnostics'
    else:
        status['last_observed_device_state']=status['current_device_state']
        status['current_blocker']='u03 UniXNU/DarwinBoot handoff unconfirmed; need persistent stage/error display'
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Recorded Android return and 14 matching partition hashes; restart actor unknown')
