#!/usr/bin/env python3
"""Import a previously checked scope into this one phone's Linux source tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))


def main(scope):
    if os.geteuid() == 0: raise SystemExit('Run as rembuild.')
    report = json.loads((ROOT / 'evidence' / f'vendor-{scope}-verification.json').read_text())
    if report['status'] != 'matches_lists': raise SystemExit('Unresolved vendor verification differences.')
    records = json.loads((ROOT / 'evidence/vendor-downloads.json').read_text())
    record = next(row for row in records if row['scope'] == scope)
    archive_path = ROOT / 'tools/vendor-sources' / (scope + '.tar.gz')
    sha = hashlib.sha256()
    with archive_path.open('rb') as stream:
        while block := stream.read(1024 * 1024): sha.update(block)
    if sha.hexdigest() != record['archive_sha256']: raise SystemExit('Archive changed after download.')
    destination = WORKSPACE / 'vendor/xiaomi' / scope
    if destination.exists(): raise SystemExit('Existing vendor directory preserved; inspect before replacing it.')
    if shutil.disk_usage('/mnt/d').free < 40 * 1024 ** 3: raise SystemExit('Low physical disk space.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.rem-vendor-' + scope + '-', dir=destination.parent))
    prefix = f"proprietary_vendor_xiaomi-{record['revision']}-{record['revision']}-{scope}"
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != prefix or '..' in parts: raise ValueError('Unexpected archive member')
            if len(parts) == 1 and member.isdir(): continue
            if len(parts) < 2 or parts[1] != scope: raise ValueError('Wrong vendor scope')
            relative = Path(*parts[2:])
            target = staging / relative
            if not target.resolve().is_relative_to(staging): raise ValueError('Out-of-scope archive path')
            if member.isdir(): target.mkdir(parents=True, exist_ok=True); continue
            if not member.isfile(): raise ValueError('Special archive member refused')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            target.chmod((member.mode & 0o555) | 0o600)
    for replacement in report.get('pinned_replacements', []):
        source = (ROOT / replacement['source_file']).resolve()
        target = (staging / replacement['path']).resolve()
        if not source.is_relative_to(ROOT / 'tools/vendor-sources/pinned-replacements' / scope):
            raise ValueError('Out-of-scope replacement source')
        if not target.is_relative_to(staging) or not target.is_file():
            raise ValueError('Replacement target is not an existing vendor file')
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != replacement['sha256']:
            raise ValueError('Replacement changed after verification')
        if hashlib.sha1(data).hexdigest() != replacement['sha1']:
            raise ValueError('Replacement pin changed')
        target.write_bytes(data)
    record['pinned_replacements'] = report.get('pinned_replacements', [])
    (staging / '.rem-source.json').write_text(json.dumps(record, indent=2))
    staging.rename(destination)
    if scope == 'lavender':
        # Preserve the historical pin verification, then apply the separately
        # reviewed configs paired with these vendor libraries.
        subprocess.run([sys.executable, str(ROOT / 'scripts/fix-camera-runtime.py')], check=True)
    print(json.dumps({'scope': scope, 'installed_source': str(destination), 'phone_written': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('scope', choices=['lavender', 'sdm660-common'])
    main(parser.parse_args().scope)
