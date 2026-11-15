#!/usr/bin/env python3
"""Reconstruct a sparse, read-only source image and extract two pinned XML files.

Only supports full OTA new/zero/erase lists, never incremental patch operations.
The image is never flashed, mounted, or used as a product output.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import brotli

ROOT = Path(__file__).resolve().parents[1]
BLOCK = 4096


def main():
    source = ROOT / 'tools/vendor-sources/old-global-vendor-SOURCE-ONLY'
    receipt = json.loads((ROOT / 'evidence/old-global-camera-source.json').read_text())
    if not receipt['phone_flash_forbidden']: raise ValueError('Incorrect source use')
    if shutil.disk_usage('/mnt/d').free < 40 * 1024 ** 3: raise SystemExit('Low host disk space')
    lines = (source / 'vendor.transfer.list').read_text().splitlines()
    if lines[0] != '4' or lines[2:4] != ['0', '0']: raise ValueError('Not a supported full OTA')
    ranges, new_ranges, max_block = [], [], 0
    for line in lines[4:]:
        command, encoded = line.split()
        if command not in ('new', 'zero', 'erase'): raise ValueError('Incremental operations refused')
        values = [int(v) for v in encoded.split(',')]
        if values[0] != len(values) - 1 or values[0] % 2: raise ValueError('Invalid range encoding')
        for a, b in zip(values[1::2], values[2::2]):
            if not 0 <= a < b <= 1024 * 1024: raise ValueError('Unexpected image size')
            max_block = max(max_block, b)
            if command != 'erase': ranges.append((a, b, command))
            if command == 'new': new_ranges.append((a * BLOCK, b * BLOCK))
    ordered = sorted(ranges)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping writes are not supported')
    expected = sum(b - a for a, b in new_ranges)
    if not 0 < expected <= 1024 ** 3: raise ValueError('Unexpected decompressed size')
    scratch = Path('/home/rembuild/vendor-camera-source')
    scratch.mkdir(exist_ok=True)
    image = scratch / 'vendor-SOURCE-ONLY.raw.img'
    decoder = brotli.Decompressor()
    written, index = 0, 0
    position = new_ranges[0][0]
    with image.open('wb') as output, (source / 'vendor.new.dat.br').open('rb') as compressed:
        output.truncate(max_block * BLOCK)
        while data := compressed.read(65536):
            decoded = decoder.process(data)
            written += len(decoded)
            if written > expected: raise ValueError('Oversized decompressed data')
            cursor = 0
            while cursor < len(decoded):
                end = new_ranges[index][1]
                size = min(end - position, len(decoded) - cursor)
                output.seek(position)
                output.write(decoded[cursor:cursor + size])
                position += size
                cursor += size
                if position == end:
                    index += 1
                    if index < len(new_ranges): position = new_ranges[index][0]
        if not decoder.is_finished() or written != expected or index != len(new_ranges):
            raise ValueError('Incomplete block image')
    mismatches = json.loads((ROOT / 'evidence/vendor-lavender-verification.json').read_text())['hash_mismatches']
    matches = ROOT / 'tools/vendor-sources/camera-xml-matching'
    matches.mkdir(exist_ok=True)
    results = []
    for row in mismatches:
        relative = row['path'].removeprefix('proprietary/vendor')
        if not relative.startswith('/etc/camera/') or not relative.endswith('.xml'):
            raise ValueError('Unexpected extraction request')
        target = scratch / Path(relative).name
        command = f'dump -p {relative} {target}'
        subprocess.run(['debugfs', '-R', command, str(image)], check=True, capture_output=True)
        data = target.read_bytes()
        digest = hashlib.sha1(data).hexdigest()
        ok = digest in row['expected']
        if ok: (matches / target.name).write_bytes(data)
        results.append({'path': row['path'], 'source': receipt['source_url'],
                        'sha1': digest, 'matches_pinned_hash': ok})
    (ROOT / 'evidence/camera-config-original-verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results))
    if not results or not all(r['matches_pinned_hash'] for r in results):
        raise SystemExit('Camera configuration still requires review')
    # Only this generated raw scratch image is discarded after exact hashes match.
    if image.resolve().parent != scratch.resolve(): raise ValueError('Unexpected scratch location')
    image.unlink()


if __name__ == '__main__': main()
