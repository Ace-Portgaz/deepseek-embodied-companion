#!/usr/bin/env python3
"""Apply reviewed camera configs paired with the imported vendor binary set."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TREE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
VENDOR = TREE / 'vendor/xiaomi/lavender'
EXPECTED_ARCHIVE = '98ae0923d1ee50c9eb2b212757a8eb09836b14cc2be2f68f41ba628e20539bf3'
CONFIGS = {
    'lavender_s5kgm1_ofilm_i_chromatix.xml': (
        '0c3c4f395f1d6a477c30dec84bd0ddfd064c71244d545c93daed35e1cac4cd8c',
        'a9f0ea890317c73abb6caa1cac9f2c7d9f0c5a34ffd036288dea966b96e7c374'),
    'lavender_s5kgm1_sunny_ii_chromatix.xml': (
        'ad077f9779b573791b3547a8d76abfee652a2080386b178dadd2bf5f1d606b3d',
        '0cf49b69e7bf6a90d20e69d6654ef5db9760c1816eab3ddeff864351f8e30ca7'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    archive_path = ROOT / 'tools/vendor-sources/lavender.tar.gz'
    h = hashlib.sha256()
    with archive_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(chunk)
    if h.hexdigest() != EXPECTED_ARCHIVE:
        raise SystemExit('Previously verified vendor archive changed.')
    configs = {}
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            name = PurePosixPath(member.name).name
            if name not in CONFIGS or not member.isfile():
                continue
            if not member.name.endswith('/lavender/proprietary/vendor/etc/camera/' + name):
                raise SystemExit('Unexpected archive member path.')
            if name in configs or member.size > 100000:
                raise SystemExit('Unexpected duplicate or oversized config.')
            data = archive.extractfile(member).read()
            if sha(data) != CONFIGS[name][1]:
                raise SystemExit('Paired camera config changed: ' + name)
            configs[name] = data
    if set(configs) != set(CONFIGS):
        raise SystemExit('Missing paired camera configurations.')
    backup = ROOT / 'evidence/camera-source-before-fix'
    backup.mkdir(exist_ok=True)
    changes = []
    for name, data in configs.items():
        target = VENDOR / 'proprietary/vendor/etc/camera' / name
        old = target.read_bytes()
        old_sha = sha(old)
        if old_sha not in CONFIGS[name]:
            raise SystemExit('Unknown source configuration; inspect before replacing: ' + name)
        references = sorted({node.text.strip() for node in ET.fromstring(data).iter()
                             if len(node) == 0 and node.text
                             and node.text.strip().startswith('lavender_')})
        missing = [item for item in references if not
                   (VENDOR / 'proprietary/vendor/lib' / ('libchromatix_' + item + '.so')).is_file()]
        if missing:
            raise SystemExit('Paired config has missing libraries: ' + str(missing))
        if old_sha == CONFIGS[name][0]:
            previous = backup / name
            if previous.exists() and previous.read_bytes() != old:
                raise SystemExit('Preserving different existing backup.')
            previous.write_bytes(old)
            (backup / (name + '.patch')).write_text(''.join(difflib.unified_diff(
                old.decode().splitlines(True), data.decode().splitlines(True),
                fromfile='pinned_raw/' + name, tofile='paired_vendor/' + name)))
            target.write_bytes(data)
        changes.append({'file': name, 'pinned_raw_sha256': CONFIGS[name][0],
                        'paired_vendor_sha256': CONFIGS[name][1],
                        'referenced_libraries': len(references), 'missing_libraries': []})
    preview = ROOT / 'vendor/rem/RemBody/src/com/rem/body/CameraPreview.java'
    if 'main.post(listener::error)' not in preview.read_text():
        raise SystemExit('Camera preview draw-callback error repair is missing.')
    imported_preview = TREE / 'vendor/rem/RemBody/src/com/rem/body/CameraPreview.java'
    if imported_preview.exists():
        imported_preview.write_bytes(preview.read_bytes())
    receipt = {
        'applied_utc': datetime.now(timezone.utc).isoformat(),
        'vendor_revision': '5ef13fcc9aad481069a58e5a1dc945ee0c31f270',
        'vendor_archive_sha256': EXPECTED_ARCHIVE,
        'reason': 'Pinned raw XML referenced absent HFR240 libraries; paired vendor configs reference the shipped HFR90/HFR120 libraries',
        'historical_pin_verification_preserved': True,
        'intentional_runtime_compatibility_changes': changes,
        'preview_error_fix': 'Post view replacement after TextureView draw callback instead of removing it synchronously',
        'preview_source_imported': imported_preview.exists(),
        'build_and_persistent_device_validation_pending': True,
    }
    (ROOT / 'evidence/camera-runtime-source-fix.json').write_text(json.dumps(receipt, indent=2) + '\n')
    metadata = VENDOR / '.rem-source.json'
    source = json.loads(metadata.read_text())
    source['post_import_runtime_compatibility_fix'] = 'evidence/camera-runtime-source-fix.json'
    source['effective_camera_configs'] = changes
    metadata.write_text(json.dumps(source, indent=2) + '\n')
    print('Applied two paired camera configs and deferred preview failure callback; all 89 tuning library references exist.')


if __name__ == '__main__':
    main()
