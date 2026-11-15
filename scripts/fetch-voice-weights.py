"""Download the pinned public GPT-SoVITS weights only; no voice samples."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / 'rem-voice'
DEST = VOICE / 'GPT-SoVITS-v2Pro/GPT_SoVITS/pretrained_models'


def verified(path, item):
    if not path.is_file() or path.stat().st_size != item['size']:
        return False
    algorithm = 'sha256' if item.get('lfs') else 'sha1'
    digest = hashlib.new(algorithm)
    if algorithm == 'sha1':
        digest.update(f"blob {item['size']}\0".encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    expected = item['lfs']['oid'] if item.get('lfs') else item['oid']
    return digest.hexdigest() == expected


def main():
    manifest = json.loads((VOICE / 'model-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in item['path']:
            raise SystemExit('Invalid manifest path')
        destination = DEST.joinpath(*relative.parts)
        if verified(destination, item):
            print('Verified existing', item['path'])
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.part')
        url = f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{item['path']}"
        with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as output:
            total = 0
            while block := response.read(1024**2):
                total += len(block)
                if total > item['size']:
                    raise ValueError('Download larger than pinned manifest: ' + item['path'])
                output.write(block)
        if not verified(temporary, item):
            raise ValueError('Size/hash mismatch: ' + item['path'])
        temporary.replace(destination)
        print('Downloaded and verified', item['path'])


if __name__ == '__main__':
    main()
