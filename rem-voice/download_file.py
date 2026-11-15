import argparse
import hashlib
from pathlib import Path
import time
import requests

p = argparse.ArgumentParser()
p.add_argument('url')
p.add_argument('output')
p.add_argument('--sha256', required=True)
a = p.parse_args()
if len(a.sha256) not in (8, 64):
    raise ValueError('Expected full SHA256 or an official 8-character checkpoint hash prefix')
dst = Path(a.output)
part = dst.with_name(dst.name + '.part')
dst.parent.mkdir(parents=True, exist_ok=True)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

if dst.exists() and digest(dst).startswith(a.sha256):
    print('ALREADY_VERIFIED', dst, flush=True)
else:
    for attempt in range(20):
        try:
            offset = part.stat().st_size if part.exists() else 0
            print('DOWNLOAD', attempt + 1, 'resume_bytes', offset, flush=True)
            with requests.get(a.url, headers={'Range': f'bytes={offset}-'} if offset else {}, stream=True, timeout=(20, 45)) as r:
                r.raise_for_status()
                append = offset > 0 and r.status_code == 206
                if append and not r.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Invalid Content-Range')
                total = int(r.headers.get('Content-Length', 0)) + (offset if append else 0)
                checkpoint = time.monotonic()
                with part.open('ab' if append else 'wb') as f:
                    for chunk in r.iter_content(1024 * 1024):
                        f.write(chunk)
                        if time.monotonic() - checkpoint > 15:
                            print('PROGRESS', f.tell(), '/', total, flush=True)
                            checkpoint = time.monotonic()
            if not digest(part).startswith(a.sha256):
                raise RuntimeError('SHA256 mismatch; refusing to install')
            part.replace(dst)
            print('VERIFIED', dst, flush=True)
            break
        except Exception as e:
            print(type(e).__name__, str(e), flush=True)
            if attempt == 19:
                raise
            time.sleep(3)
