"""Import only the reviewed Android character assets from the user ZIP."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__import__('os').environ.get('REM_CHARACTER_ZIP', str(ROOT / 'delivery/Rem_Expressive_Bust_v5_1_Gyro.zip')))
PREFIX = 'Rem_Expressive_Bust_v5_1_Gyro/'
COMPONENT = ROOT / 'vendor/rem/RemBody'


def main():
    backup = ROOT / 'evidence/visual-integration-before'
    backup.mkdir(exist_ok=True)
    for relative in ('Android.bp', 'AndroidManifest.xml', 'src/com/rem/body/RemActivity.java',
                     'src/com/rem/body/BodyState.java', 'src/com/rem/body/CameraPreview.java'):
        source = COMPONENT / relative
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise SystemExit('Preserving original pre-integration source: ' + relative)
        shutil.copyfile(source, target)
    imported = []
    with zipfile.ZipFile(PACKAGE) as archive:
        if archive.testzip():
            raise SystemExit('Character archive CRC failure.')
        for info in archive.infolist():
            name = info.filename
            parts = PurePosixPath(name).parts
            if '..' in parts or name.startswith('/') or '\\' in name or stat.S_ISLNK(info.external_attr >> 16):
                raise SystemExit('Unsafe archive member: ' + name)
            if info.is_dir():
                continue
            if name.startswith(PREFIX + 'android-assets/'):
                relative = 'assets/' + name[len(PREFIX + 'android-assets/'):]
            elif name.startswith(PREFIX + 'android/'):
                relative = 'src/' + name[len(PREFIX + 'android/'):]
            elif name.startswith(PREFIX + 'licenses/'):
                relative = 'assets/character-licenses/' + name[len(PREFIX + 'licenses/'):]
            else:
                continue
            data = archive.read(info)
            target = COMPONENT / relative
            if target.exists() and target.read_bytes() != data:
                raise SystemExit('Preserving different integration file: ' + relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            imported.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    receipt = {'imported_utc': datetime.now(timezone.utc).isoformat(), 'source_zip': str(PACKAGE),
               'source_sha256': hashlib.sha256(PACKAGE.read_bytes()).hexdigest(),
               'zip_crc_passed': True, 'files': imported, 'original_archive_unchanged': True,
               'model_art_and_mesh_changes': False, 'phone_updated': False}
    (ROOT / 'evidence/visual-character-import.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files_imported': len(imported), 'bytes': sum(i['bytes'] for i in imported),
                      'zip_sha256': receipt['source_sha256']}))


if __name__ == '__main__':
    main()
