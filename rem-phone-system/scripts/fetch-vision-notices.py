"""Keep upstream redistribution notices alongside the offline runtime."""
from pathlib import Path
import urllib.request
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'vendor/rem/RemBody/assets/vision/licenses'
URLS={
 'PROTOBUF-LICENSE.txt':'https://raw.githubusercontent.com/protocolbuffers/protobuf/v26.1/LICENSE',
 'GUAVA-LICENSE.txt':'https://raw.githubusercontent.com/google/guava/v27.0.1/COPYING',
 'FLOGGER-LICENSE.txt':'https://raw.githubusercontent.com/google/flogger/flogger-0.6/LICENSE',
}
DEST.mkdir(exist_ok=True)
rows=[]
for name,url in URLS.items():
    data=urllib.request.urlopen(url,timeout=30).read()
    if len(data)<100:raise ValueError('Unexpected license response.')
    (DEST/name).write_bytes(data)
    rows.append({'file':name,'url':url,'sha256':hashlib.sha256(data).hexdigest()})
dependency=DEST.parent/'DEPENDENCIES.txt'
dependency.write_text(dependency.read_text(encoding='utf-8').replace('(see libs META-INF/LICENSE)','(see licenses/PROTOBUF-LICENSE.txt)'),encoding='utf-8')
(ROOT/'evidence/vision-license-sources.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Downloaded upstream redistribution licenses with source hashes.')
