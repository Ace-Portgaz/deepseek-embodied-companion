"""Inspect scoped vendor archives; compare blobs against pinned device-tree lists.

Does not extract archives or execute vendor makefiles. Unpinned entries are reported
as present only, not as hash-verified. Multiple hashes allow listed fixup variants.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

REVISION = '5ef13fcc9aad481069a58e5a1dc945ee0c31f270'


def verify(root, scope):
    archive_path = root / 'tools/vendor-sources' / (scope + '.tar.gz')
    source_dir = root.parent / 'upstream' / ('android_device_xiaomi_' + scope)
    source_lists = [source_dir / 'proprietary-files.txt']
    if scope == 'sdm660-common':
        source_lists += [source_dir / 'proprietary-files-fm.txt', source_dir / 'proprietary-files-ir.txt']
    required = {}
    lines = [line for source in source_lists for line in source.read_text(encoding='utf-8').splitlines()]
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'): continue
        parts = line.split('|')
        target = parts[0].lstrip('-').split(';', 1)[0].split(':')[-1]
        hashes = parts[1:]
        if any(not re.fullmatch('[a-f0-9]{40}', h) for h in hashes):
            raise ValueError('Unsupported pinned hash in ' + target)
        if 'proprietary/' + target in required and required['proprietary/' + target] != hashes:
            raise ValueError('Conflicting pinned hashes')
        required['proprietary/' + target] = hashes
    expected_root = f'proprietary_vendor_xiaomi-{REVISION}-{REVISION}-{scope}'
    seen, matched, mismatches, review = set(), [], [], {}
    total = 0
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != expected_root:
                raise ValueError('Unexpected archive path')
            if len(path.parts) == 1 and member.isdir(): continue
            if len(path.parts) < 2 or path.parts[1] != scope:
                raise ValueError('Archive exceeds requested device scope')
            if member.isdir(): continue
            if not member.isfile() or member.size > 512 * 1024 ** 2:
                raise ValueError('Unsupported archive member')
            total += member.size
            if total > 2 * 1024 ** 3: raise ValueError('Archive expands beyond two GiB')
            relative = '/'.join(path.parts[2:])
            seen.add(relative)
            with archive.extractfile(member) as stream:
                if relative in required and required[relative]:
                    sha = hashlib.sha1()
                    while block := stream.read(1024 * 1024): sha.update(block)
                    if sha.hexdigest() in required[relative]: matched.append(relative)
                    else: mismatches.append({'path': relative, 'actual': sha.hexdigest(), 'expected': required[relative]})
                elif relative in ('Android.mk', 'BoardConfigVendor.mk', scope + '-vendor.mk', 'Android.bp'):
                    if member.size > 2 * 1024 ** 2: raise ValueError('Unusually large build definition')
                    content = stream.read().decode('utf-8')
                    review[relative] = [line for line in content.splitlines()
                                        if re.search(r'\$\(shell|https?://|\b(curl|wget|eval|python|bash)\b', line)]
    missing = sorted(set(required) - seen)
    # Keep the original archive differences in the receipt. Only exact pinned
    # replacement bytes may resolve them; upstream pins are never relaxed.
    archive_mismatches = list(mismatches)
    replacements = []
    replacement_root = root / 'tools/vendor-sources/pinned-replacements' / scope
    for difference in archive_mismatches:
        candidate = replacement_root / difference['path']
        if not candidate.is_file(): continue
        data = candidate.read_bytes()
        if hashlib.sha1(data).hexdigest() not in difference['expected']:
            raise ValueError('Replacement does not match upstream pin: ' + difference['path'])
        replacements.append({'path': difference['path'],
                             'source_file': candidate.relative_to(root).as_posix(),
                             'sha1': hashlib.sha1(data).hexdigest(),
                             'sha256': hashlib.sha256(data).hexdigest()})
        matched.append(difference['path'])
        mismatches.remove(difference)
    report = {'scope': scope, 'revision': REVISION, 'source_lists': [s.name for s in source_lists], 'required_entries': len(required),
              'pinned_entries': sum(bool(h) for h in required.values()),
              'hash_matches': len(matched), 'missing': missing, 'hash_mismatches': mismatches,
              'archive_hash_mismatches': archive_mismatches, 'pinned_replacements': replacements,
              'unpinned_entries_present': sum(not required[p] for p in required if p in seen),
              'unpacked_bytes': total, 'build_definition_review_lines': review,
              'extracted': False, 'status': 'matches_lists' if not missing and not mismatches else 'review_required'}
    target = root / 'evidence' / ('vendor-' + scope + '-verification.json')
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'build_definition_review_lines'}))
    return 0 if report['status'] == 'matches_lists' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('scope', choices=['lavender', 'sdm660-common'])
    args = parser.parse_args()
    raise SystemExit(verify(Path(__file__).resolve().parents[1], args.scope))
