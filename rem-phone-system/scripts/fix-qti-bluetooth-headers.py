#!/usr/bin/env python3
"""Declare the AOSP header dependency introduced by the LE security backport."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

TREE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
EVIDENCE = Path(__file__).resolve().parents[1] / 'evidence'
repository = TREE / 'vendor/qcom/opensource/commonsys/system/bt'
target = repository / 'stack/Android.bp'
before = target.read_text()
anchor = '        "system/bt/embdrv/sbc/decoder/include",\n'
addition = anchor + '        // LE encryption backport uses PRIVATE_ADDRESS from main/shim/dumpsys.h.\n        "system/bt",\n'
if before.count(anchor) != 1:
    raise SystemExit('Unexpected Bluetooth build file; inspect before modifying.')
header = TREE / 'system/bt/main/shim/dumpsys.h'
if '#define PRIVATE_ADDRESS(addr)' not in header.read_text():
    raise SystemExit('The required address-redaction header is unavailable.')
if addition not in before:
    target.write_text(before.replace(anchor, addition))
patch = subprocess.check_output(['git', 'diff', '--', 'stack/Android.bp'], cwd=repository)
(EVIDENCE / 'qti-bluetooth-shim-header.patch').write_bytes(patch)
receipt = {
    'updated_utc': datetime.now(timezone.utc).isoformat(),
    'repository_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip(),
    'backport_commit': 'e56649c74adb1df416e386ee70bc6103896377e4',
    'failure': 'btm_acl.cc cannot resolve main/shim/dumpsys.h',
    'fix': 'Add the existing AOSP system/bt include root to libbt-stack_qti only.',
    'le_encryption_logic_unchanged': True,
    'private_address_redaction_unchanged': True,
    'header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
    'patch_sha256': hashlib.sha256(patch).hexdigest(),
    'target_validation': 'pending',
    'full_rom_built': False,
}
(EVIDENCE / 'bluetooth-build-fix.json').write_text(json.dumps(receipt, indent=2))
print('Declared the existing shim header include path; security backport retained.')
