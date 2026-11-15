"""Download pinned public vision libraries/models using verified HTTPS."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'tools/vision-dependencies'
VERSION = '0.10.35'
FILES = {
    'tasks-vision.aar': f'https://dl.google.com/dl/android/maven2/com/google/mediapipe/tasks-vision/{VERSION}/tasks-vision-{VERSION}.aar',
    'tasks-core.aar': f'https://dl.google.com/dl/android/maven2/com/google/mediapipe/tasks-core/{VERSION}/tasks-core-{VERSION}.aar',
    'face_landmarker.task': 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
    'gesture_recognizer.task': 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task',
    'guava.jar': 'https://repo.maven.apache.org/maven2/com/google/guava/guava/27.0.1-android/guava-27.0.1-android.jar',
    'failureaccess.jar': 'https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.1/failureaccess-1.0.1.jar',
    'protobuf-javalite.jar': 'https://repo.maven.apache.org/maven2/com/google/protobuf/protobuf-javalite/4.26.1/protobuf-javalite-4.26.1.jar',
    'flogger.jar': 'https://repo.maven.apache.org/maven2/com/google/flogger/flogger/0.6/flogger-0.6.jar',
    'flogger-system-backend.jar': 'https://repo.maven.apache.org/maven2/com/google/flogger/flogger-system-backend/0.6/flogger-system-backend-0.6.jar',
    'androidx-annotation.jar': 'https://dl.google.com/dl/android/maven2/androidx/annotation/annotation/1.1.0/annotation-1.1.0.jar',
    'MEDIAPIPE-LICENSE.txt': f'https://raw.githubusercontent.com/google-ai-edge/mediapipe/v{VERSION}/LICENSE',
}


def fetch(item):
    name, url = item
    path = DEST / name
    if not path.exists():
        data = urllib.request.urlopen(url, timeout=60).read()
        if len(data) < 100:
            raise ValueError('Unexpected download: ' + name)
        temp = path.with_suffix(path.suffix + '.part')
        temp.write_bytes(data)
        temp.replace(path)
    data = path.read_bytes()
    if name.endswith(('.aar', '.jar', '.task')):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise ValueError('Archive corruption: ' + name)
    return {'name': name, 'url': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, FILES.items()))
    receipt = {'downloaded_utc': datetime.now(timezone.utc).isoformat(),
               'mediapipe_version': VERSION, 'files': rows, 'tls_verification_enabled': True}
    (DEST / 'download-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    for row in rows:
        print(row['name'] + ': ' + str(row['bytes']) + ' bytes, SHA256 ' + row['sha256'])
    for name in ('tasks-core.aar', 'tasks-vision.aar'):
        with zipfile.ZipFile(DEST / name) as archive:
            print(name + ' entries: ' + json.dumps(archive.namelist()))
            print(name + ' manifest: ' + archive.read('AndroidManifest.xml').decode())
            (DEST / name.replace('.aar', '-classes.jar')).write_bytes(archive.read('classes.jar'))


if __name__ == '__main__':
    main()
