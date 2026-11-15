"""Read only vendor entries from Xiaomi's old OTA archive via verified HTTP ranges.

The archive is a source of two pinned camera XML files, NOT a flash candidate.
No old boot/system/firmware images are downloaded or written to the phone.
"""
import io
import json
from pathlib import Path
import urllib.request
import zipfile

URL = ('https://cdnorg.d.miui.com/V10.3.6.0.PFGMIXM/'
       'miui_LAVENDERGlobal_V10.3.6.0.PFGMIXM_8c74282d30_9.0.zip')
LENGTH = 1819701120
ROOT = Path(__file__).resolve().parents[1]


class RangeFile(io.RawIOBase):
    def __init__(self): self.position = 0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        base = {0: 0, 1: self.position, 2: LENGTH}[whence]
        position = base + offset
        if position < 0 or position > LENGTH: raise ValueError('Range out of bounds')
        self.position = position
        return position
    def read(self, size=-1):
        size = LENGTH - self.position if size < 0 else min(size, LENGTH - self.position)
        if not size: return b''
        if size > 32 * 1024 ** 2: raise ValueError('Unexpected oversized range')
        start, end = self.position, self.position + size - 1
        url = URL + f'?rem-range={start}-{end}'
        request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{LENGTH}':
                raise ValueError('Server did not honor the exact byte range')
            content = response.read(size + 1)
        if len(content) != size: raise ValueError('Truncated range')
        self.position += size
        return content


def main():
    destination = ROOT / 'tools/vendor-sources/old-global-vendor-SOURCE-ONLY'
    destination.mkdir(parents=True, exist_ok=True)
    reports = []
    with zipfile.ZipFile(RangeFile()) as archive:
        names = archive.namelist()
        wanted = [name for name in names if name in ('vendor.transfer.list', 'vendor.new.dat.br', 'vendor.new.dat')]
        print(json.dumps({'vendor_entries': wanted}), flush=True)
        if 'vendor.transfer.list' not in wanted or not any(n.startswith('vendor.new.dat') for n in wanted):
            raise ValueError('Expected a full vendor block image')
        for name in sorted(wanted, key=lambda n: not n.endswith('.list')):
            info = archive.getinfo(name)
            if info.file_size > 1024 ** 3 or info.compress_size > 1024 ** 3:
                raise ValueError('Vendor member exceeds expected size')
            target = destination / (name + '.partial')
            with archive.open(name) as stream, target.open('wb') as output:
                while block := stream.read(1024 * 1024): output.write(block)
            target.replace(destination / name)
            reports.append({'name': name, 'bytes': info.file_size, 'zip_crc_verified': True})
            print(json.dumps(reports[-1]), flush=True)
    (ROOT / 'evidence/old-global-camera-source.json').write_text(json.dumps({
        'source_url': URL, 'purpose': 'camera configuration provenance only',
        'phone_flash_forbidden': True, 'members': reports}, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
