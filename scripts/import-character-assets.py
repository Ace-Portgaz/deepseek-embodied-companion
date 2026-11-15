"""Restore missing model assets from the user's ZIP, preserving current code."""
import argparse
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'rem-phone-system/vendor/rem/RemBody/assets'
PREFIX = 'Rem_Expressive_Bust_v5_1_Gyro/android-assets/'
ALLOWED = {'.moc3', '.png', '.jpg', '.jpeg', '.webp', '.json', '.js'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip_path', type=Path)
    parser.add_argument('--apply', action='store_true', help='Write validated missing files; default only lists them')
    args = parser.parse_args()
    pending = []
    total = 0
    with zipfile.ZipFile(args.zip_path) as archive:
        for entry in archive.infolist():
            name = entry.filename
            if not name.startswith(PREFIX) or entry.is_dir():
                continue
            relative = PurePosixPath(name[len(PREFIX):])
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or stat.S_ISLNK(entry.external_attr >> 16):
                raise SystemExit('Unsafe archive member')
            destination = DEST.joinpath(*relative.parts)
            if not destination.resolve().is_relative_to(DEST.resolve()):
                raise SystemExit('Asset path escapes destination')
            if destination.exists():
                continue  # Current rendering/vision/voice code always wins.
            if destination.suffix.lower() not in ALLOWED:
                continue
            # Only SDK/vendor JS may be restored; application JS is already in Git.
            if destination.suffix == '.js' and 'vendor' not in relative.parts:
                continue
            total += entry.file_size
            if entry.file_size > 128 * 1024**2 or total > 1024**3:
                raise SystemExit('Asset archive exceeds expected size')
            pending.append((entry, destination))
        for entry, destination in pending:
            print(destination.relative_to(ROOT))
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                # ZipFile.read verifies this member's CRC.
                with destination.open('xb') as output:
                    output.write(archive.read(entry))
    print(f'{len(pending)} missing assets, {total} bytes; ' + ('imported' if args.apply else 'dry run; add --apply to import'))


if __name__ == '__main__':
    main()
