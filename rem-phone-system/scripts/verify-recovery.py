"""Verify and inspect the stock package without extracting or executing its scripts."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "recovery/lavender_V12.5.7.0_stock.tgz"
PART = FILE.with_name(FILE.name + ".partial")
EXPECTED_BYTES = 3520497659
EXPECTED_MD5 = "8b85782ef691926674297f955f6801f2"
URL = ("https://cdnorg.d.miui.com/V12.5.7.0.QFGCNXM/"
       "lavender_images_V12.5.7.0.QFGCNXM_20211109.0000.00_10.0_cn_8b85782ef6.tgz")


def main():
    source = FILE if FILE.exists() else PART
    if source.stat().st_size != EXPECTED_BYTES:
        raise SystemExit("Download incomplete; no package promoted to verified state.")
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with source.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            md5.update(block)
            sha256.update(block)
    if md5.hexdigest() != EXPECTED_MD5:
        raise SystemExit("Checksum mismatch; do not flash or extract this package.")
    entries, metadata = [], {}
    wanted = {"flash_all.bat", "flash_all.sh", "flash_all_lock.bat",
              "android-info.txt", "anti_version.txt"}
    with tarfile.open(source, "r|gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unexpected unsafe archive member.")
            entries.append({"name": member.name, "size": member.size, "file": member.isfile()})
            if path.name in wanted and member.isfile() and member.size < 65536:
                with archive.extractfile(member) as stream:
                    metadata[member.name] = stream.read().decode("utf-8", errors="replace")
    for required in ("boot.img", "recovery.img", "system.img", "vendor.img"):
        if not any(PurePosixPath(row["name"]).name == required and row["file"] for row in entries):
            raise SystemExit("Missing stock image: " + required)
    if source == PART:
        PART.rename(FILE)
    report = {"status": "download_integrity_verified_not_flash_tested", "source_url": URL,
              "bytes": EXPECTED_BYTES, "md5": md5.hexdigest(), "sha256": sha256.hexdigest(),
              "model": "lavender", "build": "V12.5.7.0.QFGCNXM", "region": "CN",
              "checksum_note": "MD5 matches the indexed checksum and filename prefix; HTTPS source is Xiaomi. SHA256 calculated locally.",
              "entries": entries, "metadata": metadata,
              "scripts_executed": False, "phone_written": False}
    target = ROOT / "evidence/recovery-verification.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "sha256": report["sha256"],
                      "entries": len(entries), "metadata_files": list(metadata)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
