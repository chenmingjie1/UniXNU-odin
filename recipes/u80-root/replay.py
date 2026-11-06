"""Print or run the pinned historical System transformation chain (Python 3.11+)."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
import sys

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True, help='Historical system.apfs, or u37 when --start u59')
    parser.add_argument('--kernel', type=Path, help='Decoded original 20F66 kernel Mach-O; required for full replay')
    parser.add_argument('--start', choices=('baseline', 'u59'), default='baseline')
    parser.add_argument('--run', action='store_true', help='Execute; default only prints commands and hashes')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    plan = json.loads((root / 'replay-plan.json').read_text(encoding='utf-8'))['steps']
    if args.start == 'u59':
        plan = plan[-2:]
    base = args.base.resolve()
    media = root / 'build/root-media'
    commands = []
    for i, step in enumerate(plan):
        source = base if i == 0 else media / step['source']
        output = media / step['output']
        values = {'base': str(base), 'source': str(source), 'output': str(output),
                  'kernel': str(args.kernel.resolve()) if args.kernel else '<original-20F66-kernel.macho>'}
        command = [sys.executable, str(root / 'scripts' / step['command'][0])]
        command += [a.format(**values) for a in step['command'][1:]]
        commands.append((step, source, output, command))
        print(shlex.join(command))
        print('  output SHA256:', step['sha256'])
    if not args.run:
        print('Plan only. Add --run after supplying the pinned inputs. Outputs are never overwritten.')
        return
    if args.start == 'baseline' and not args.kernel:
        parser.error('--kernel is required for the resource-map validation')
    assert digest(base) == plan[0]['source_sha256'], 'Base hash differs from historical input; no replay performed'
    if args.start == 'baseline':
        assert (root / 'inputs/rootfs/System/Library/LaunchDaemons').is_dir(), 'Extract original launchd plists first'
    for _, _, output, _ in commands:
        assert not output.exists(), 'Refusing to overwrite: ' + str(output)
    media.mkdir(parents=True, exist_ok=True)
    if args.start == 'u59':
        # prepare_host_virtual_input_root uses the historical fixed input filename.
        import shutil
        expected = media / 'system-core-policy-u37.apfs'
        if expected.resolve() != base:
            assert not expected.exists(), str(expected)
            shutil.copyfile(base, expected)
    for step, source, output, command in commands:
        assert digest(source) == step['source_sha256'], str(source)
        subprocess.run(command, cwd=root, check=True)
        assert output.stat().st_size == step['bytes'] and digest(output) == step['sha256'], 'Historical output differs: ' + str(output)
    trust = media / 'host-input-development-trust-u80.bundle'
    assert digest(trust) == '470b02f3596768ac02f74ba4ea2ad10a271bbfb5d91858d499062edc7950b600'
    print('All selected stages and final u80 trust bundle match the historical SHA256 values.')

if __name__ == '__main__':
    main()
