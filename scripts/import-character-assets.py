"""Import a user-supplied Live2D model; dry-run by default. No SDK or app code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'rem-phone-system/vendor/rem/RemBody/assets/rem-bust-v4'
ALLOWED = {'.moc3', '.png', '.jpg', '.jpeg', '.webp', '.json', '.txt', '.md'}


def safe_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe asset path')
    return path


def plan(archive, selected=None):
    entries = {}
    for item in archive.infolist():
        if item.is_dir():
            continue
        safe_path(item.filename)
        if stat.S_ISLNK(item.external_attr >> 16) or item.filename in entries:
            raise ValueError('Symlink or duplicate archive member')
        entries[item.filename] = item
    models = [name for name in entries if name.endswith('.model3.json')]
    if selected is None:
        if len(models) != 1:
            raise ValueError('Specify --model with one of these archive paths: '+repr(models))
        selected = models[0]
    if selected not in models:
        raise ValueError('Selected model is not in this archive')
    folder = PurePosixPath(selected).parent
    pending = []
    total = 0
    for name, entry in entries.items():
        try:
            rel = PurePosixPath(name).relative_to(folder)
        except ValueError:
            filename = PurePosixPath(name).name
            if PurePosixPath(name).suffix.lower() not in {'.txt','.md'} or not any(word in filename.lower() for word in ('license','terms','usage','许可','使用说明')):
                continue
            rel = PurePosixPath('licenses') / filename
        if rel.suffix.lower() not in ALLOWED:
            continue
        total += entry.file_size
        if entry.file_size > 128*1024**2 or total > 1024**3:
            raise ValueError('Model exceeds expected size')
        pending.append((entry, rel))
    settings = json.loads(archive.read(entries[selected]))
    references = settings.get('FileReferences', {})
    def paths(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for child in value:
                yield from paths(child)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key not in {'Name', 'FadeInTime', 'FadeOutTime'}:
                    yield from paths(child)
    included = {rel.as_posix() for _, rel in pending}
    if len(included) != len(pending):
        raise ValueError('Duplicate destination asset path')
    if not isinstance(references.get('Moc'), str):
        raise ValueError('Missing Moc reference')
    for name in paths(references):
        safe_path(name)
        if name not in included:
            raise ValueError('Missing or unsupported model resource: '+name)
    return selected, references['Moc'], pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip_path', type=Path)
    parser.add_argument('--model', help='Exact .model3.json path within a multi-model ZIP')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    destination = BASE/'models/deepseek-chan-user'
    catalog_path = BASE/'catalog.json'
    with zipfile.ZipFile(args.zip_path) as archive:
        selected, moc, pending = plan(archive, args.model)
        for _, rel in pending:
            print(rel.as_posix())
        if not args.apply:
            print(f'{len(pending)} files; dry run. Add --apply to import.')
            return
        if destination.exists() or catalog_path.exists():
            raise SystemExit('Existing model or catalog found; preserve it and choose a clean import workspace.')
        if not destination.resolve().is_relative_to(BASE.resolve()):
            raise SystemExit('Asset destination escapes root')
        destination.mkdir(parents=True)
        for entry, rel in pending:
            target = destination.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(archive.read(entry))
        prefix = 'models/deepseek-chan-user/'
        catalog = {'version':8, 'kind':'live2d-companion', 'defaultOutfit':'deepseek-chan-user', 'outfits':[{
            'id':'deepseek-chan-user', 'name':'大肥鱼 · DeepSeek-chan 全身',
            'model':prefix+PurePosixPath(selected).name, 'interaction':prefix+'interaction.json',
            'sha256':hashlib.sha256((destination/moc).read_bytes()).hexdigest(),
            'framing':{'width':1,'height':1}, 'view':'full',
            'attribution':'Illustration / PSD: Kamiya Ryoko; Live2D: 霓虹猫_NeonNeko. https://vgen.co/KAMIYA'}]}
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Imported. Prepare Cubism Core, then run node scripts/build-character-interaction.cjs.')


if __name__ == '__main__':
    main()
