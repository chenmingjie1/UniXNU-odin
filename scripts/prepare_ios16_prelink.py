"""Audit real iOS16 kexts and attempt strict native prelink without fallback bindings."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tomllib
import argparse

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / 'work/UniXNU-odin'
OUT = DEV / 'build/ios16-prelink'
INPUT = OUT
KIT = ROOT / 'work/UniXNU-components/XnuPrelink-b74ed7c74a07f0eb5f81089c660905ecc4cabb7f'
REF = ROOT / 'work/UniXNU-components/Reference-nx769j-2a265afdbd95d45e4a90664157e793c3bfee3755'
EXPECTED = 'e6fa75598f47b5a9460a60913e2ac8e4cd6cd60eb475bb31da65b68ffbcfdad5'
sys.path.insert(0, str(KIT))
import native_prelink as np
import emit_prelink as emit


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2,
        default=lambda x: {'bytes_hex': x.hex()} if isinstance(x, bytes) else x) + '\n')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, default=DEV / 'build/native-kernel/mach.development.bcm2837.unstripped')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--driver-policy',type=Path,help='Explicit board personality selection; executable code remains intact')
    args = parser.parse_args()
    OUT=args.output_dir;OUT.mkdir(parents=True,exist_ok=True)
    original = (INPUT / 'kernelcache.decompressed').read_bytes()
    native = args.kernel.read_bytes()
    assert hashlib.sha256(original).hexdigest() == EXPECTED
    parent = np.macho(original)
    info = next(s for s in parent['segments'] if s['name'] == '__PRELINK_INFO')
    at = np.backed_offset(parent['segments'], info['va'], info['filesize'], len(original))
    metadata = np.unserialize_xml(original[at:at+info['filesize']])
    entries = metadata['_PrelinkInfoDictionary']
    by_id = {e['CFBundleIdentifier']: e for e in entries}
    assert len(by_id) == len(entries), 'Duplicate IDs after real XML IDREF resolution'
    save('original-kext-metadata.json', entries)
    measured = {
        'original_sha256': EXPECTED, 'native_sha256': hashlib.sha256(native).hexdigest(),
        'parser': 'XnuPrelink.native_prelink.unserialize_xml with nested XML IDREF resolution',
        'supersedes_initial_regex_metadata': True,
        'kext_count': len(entries),
        'hid_entries': [e for e in entries if 'HID' in e['CFBundleIdentifier']],
        'iokit_event_driver_bundle_present': 'com.apple.iokit.IOHIDEventDriver' in by_id,
        'device_tested': False,
    }
    save('original-kernel-verification.json', measured)

    # Reuse the reference's exact-image literal-pool boundary checks, not its addresses blindly.
    spec = importlib.util.spec_from_file_location('ios16_pool', REF / 'scripts/emit-prelink-nx769j.py')
    pool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pool)
    prefix = pool.verify_pool(original, np)
    emit.MATH_LITERAL_POOLS = (*emit.MATH_LITERAL_POOLS,
                              (prefix, pool.LIBM_POOL_SIZE, pool.LIBM_POOL_SHA256))
    profile = tomllib.loads((REF / 'os-profiles/ios-16.5-20F66/profile.toml').read_text())
    roots = profile['kernel']['prelink']['roots']
    # The reference's regex parser missed this nested/codeless plugin.
    # Actual XML/IDREF parsing above establishes its presence and dependencies.
    if 'com.apple.iokit.IOHIDEventDriver' not in roots:
        roots.append('com.apple.iokit.IOHIDEventDriver')
    assert all(r in by_id for r in roots)
    result = {'original_sha256': EXPECTED, 'native_sha256': measured['native_sha256'],
              'roots': roots, 'slide': -0x1000000, 'literal_pool_verified': True,
              'experimental_only': True, 'device_tested': False}
    try:
        image, report = emit.emit(native, original, roots, -0x1000000)
        if args.driver_policy:
            from apply_original_driver_policy import apply
            image, report = apply(image,report,args.driver_policy,np,emit)
    except (ValueError, KeyError, StopIteration) as error:
        result.update(status='blocked', error_type=type(error).__name__, error=str(error), candidate_created=False)
        # Per-root plans identify independent failures without writing a partial image.
        plans = {}
        for root in roots:
            try:
                plan = np.plan(native, original, [root], -0x1000000)
                plans[root] = {'status': 'plan-pass', 'components': plan['components']}
            except (ValueError, KeyError, StopIteration) as exc:
                plans[root] = {'status': 'blocked', 'error': str(exc), 'error_type': type(exc).__name__}
        result['per_root_plan'] = plans
    else:
        target = OUT / 'kernel.prelinked.experimental.macho'
        if target.exists():
            assert target.read_bytes() == image
        else:
            target.write_bytes(image)
        save('prelink-emission-report.json', report)
        result.update(status='emitted-unqualified', candidate_created=True,
                      candidate_sha256=hashlib.sha256(image).hexdigest(), bytes=len(image))
    save('prelink-attempt.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('roots','per_root_plan')}, indent=2))
    print(f"Real kext count: {len(entries)}; IOHIDEventDriver separate bundle: {measured['iokit_event_driver_bundle_present']}")


if __name__ == '__main__':
    main()
