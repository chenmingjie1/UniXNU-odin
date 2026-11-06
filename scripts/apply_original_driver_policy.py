"""Apply board matching policy to emitted metadata, preserving executable code."""
import copy
import hashlib
import struct
import tomllib
import xml.etree.ElementTree as ET


def apply(image, report, policy_path, np, emitter):
    policy = tomllib.loads(policy_path.read_text())
    assert set(policy) == {'disable_personalities'}
    parsed = np.macho(image)
    segment = next(s for s in parsed['segments'] if s['name'] == '__PRELINK_INFO')
    offset = segment['fileoff']
    metadata = np.unserialize_xml(image[offset:offset+segment['filesize']])
    entries = {e['CFBundleIdentifier']:e for e in metadata['_PrelinkInfoDictionary']}
    disabled = []
    for identifier, names in policy['disable_personalities'].items():
        personalities = entries[identifier]['IOKitPersonalities']
        for name in names:
            original = personalities.pop(name)
            disabled.append({'bundle':identifier,'personality':name,'original':original})
    xml = ET.tostring(emitter.to_xml(metadata),encoding='utf-8').replace(b' />',b'/>')+b'\0'
    assert len(xml) <= segment['size']
    result = bytearray(image)
    # Preserve the mapped segment and all other file offsets. Zero its spare
    # backing bytes so removed metadata cannot be parsed accidentally.
    assert len(xml) <= segment['filesize']
    result[offset:offset+segment['filesize']] = xml + bytes(segment['filesize']-len(xml))
    struct.pack_into('<Q',result,segment['command_offset']+48,len(xml))
    output = bytes(result)
    np.macho(output)
    report = copy.deepcopy(report)
    report['board_metadata_policy'] = {
        'sha256':hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'disabled_personalities':disabled,
        'instruction_bytes_changed':False,
        'reason':'ArmDTPlatform and ArmCpu own platform/CPU matching on SM8350',
    }
    report['candidate_sha256'] = hashlib.sha256(output).hexdigest()
    return output, report
