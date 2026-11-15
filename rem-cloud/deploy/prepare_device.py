"""Prepare an NVS update, then prove every existing setting is preserved.

This script never writes the device. It uses Espressif's parser and generator.
"""
import base64
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_config import load_private, private_write, validate

PARSER = ROOT.parent / 'upstream/esp-idf-nvs-tool/nvs_tool.py'
PRIVATE = ROOT / '.private'


def parse(path):
    result = subprocess.run([sys.executable, str(PARSER), str(path), '-f', 'json', '-d', 'minimal'],
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def mapping(entries):
    result = {}
    for e in entries:
        key = e['namespace'], e['key']
        if key in result:
            raise ValueError('Duplicate/chunked NVS key requires a separate review')
        encoding = e['encoding']
        value = e['data']
        if encoding in ('blob_data', 'blob'):
            value = base64.b64decode(value, validate=True)
            encoding = 'blob'
        result[key] = encoding, value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--isolate-cloud', action='store_true')
    args = parser.parse_args()
    if args.isolate_cloud:
        raise SystemExit('Disabled: clearing this custom firmware\'s legacy settings caused reboot loops. Keep the restored configuration.')
    settings, credentials = load_private()
    if validate(settings, credentials):
        raise SystemExit('Cloud configuration is incomplete')
    source = 'device-nvs-after.bin' if args.isolate_cloud else 'device-nvs-original.bin'
    original = mapping(parse(PRIVATE / source))
    expected = dict(original)
    url = f"https://{settings['public_host']}/setup/{credentials['device_setup_secret']}/xiaozhi/ota/"
    expected[('wifi', 'ota_url')] = ('string', url)
    if args.isolate_cloud:
        for key, (encoding, value) in original.items():
            if key[0] in ('mqtt', 'httpConfig'):
                expected[key] = (encoding, '' if encoding == 'string' else 0)
    encodings = {'string': 'string', 'blob': 'hex2bin', 'uint8_t': 'u8', 'int8_t': 'i8',
                 'uint16_t': 'u16', 'int16_t': 'i16', 'uint32_t': 'u32', 'int32_t': 'i32',
                 'uint64_t': 'u64', 'int64_t': 'i64'}
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['key', 'type', 'encoding', 'value'])
    for namespace in dict.fromkeys(ns for ns, key in expected):
        writer.writerow([namespace, 'namespace', '', ''])
        for (ns, key), (encoding, value) in expected.items():
            if ns == namespace:
                writer.writerow([key, 'data', encodings[encoding], value.hex() if isinstance(value, bytes) else value])
    private_write(PRIVATE / 'device-rem.csv', stream.getvalue())
    generated = PRIVATE / 'device-nvs-rem.bin'
    subprocess.run([sys.executable, '-m', 'esp_idf_nvs_partition_gen', 'generate',
                    str(PRIVATE / 'device-rem.csv'), str(generated), '0x4000'],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    actual = mapping(parse(generated))
    if actual != expected or generated.stat().st_size != 0x4000:
        raise SystemExit('Generated settings differ from the reviewed update')
    changes = [ns+'/'+key for (ns,key),value in expected.items() if original.get((ns,key)) != value]
    proof = {'preserved_existing_keys': len(original)-sum(k in original for k in expected if expected[k]!=original.get(k)), 'changed_keys': changes,
             'partition_offset': '0x9000', 'partition_bytes': 0x4000,
             'semantic_roundtrip_verified': True, 'written_to_device': False}
    (ROOT / 'evidence/device-config-prepared.json').write_text(json.dumps(proof, indent=2))
    print('Prepared and verified device settings. Changed fields:', ', '.join(changes))


if __name__ == '__main__':
    main()
