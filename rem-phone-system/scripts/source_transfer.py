"""Read-only sampling of temporary source-pack growth, not total network traffic."""
import json
import os
from pathlib import Path
import time

WORKSPACE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))


def snapshot(group):
    files = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if os.getpgid(int(proc.name)) != group:
                continue
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if b'index-pack' not in args:
                continue
            for fd in (proc / 'fd').iterdir():
                try:
                    target = fd.readlink()
                    if not target.is_relative_to(WORKSPACE) or not target.name.startswith('tmp_pack_'):
                        continue
                    stat = fd.stat()
                    files[f'{stat.st_dev}:{stat.st_ino}'] = stat.st_size
                except OSError:
                    continue
        except (OSError, ValueError):
            continue
    return {'group': group, 'observed': time.monotonic(), 'files': files}


def estimate_rate(previous, current):
    """First sample is a baseline. Removed packs never cause a negative speed."""
    if previous is None or previous['group'] != current['group']:
        return None
    elapsed = current['observed'] - previous['observed']
    if elapsed <= 0:
        return None
    growth = sum(max(0, size - previous['files'].get(key, 0))
                 for key, size in current['files'].items())
    return growth / elapsed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', required=True, type=int)
    args = parser.parse_args()
    if args.group <= 1:
        raise SystemExit('Invalid download group')
    print(json.dumps(snapshot(args.group)))
