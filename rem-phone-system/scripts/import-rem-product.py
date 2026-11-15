#!/usr/bin/env python3
"""Stage the dedicated HOME product without touching any connected phone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TREE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
source = ROOT / 'vendor/rem'
destination = TREE / 'vendor/rem'
if destination.exists():
    raise SystemExit('Existing Rem product preserved. Review before updating.')
manifest = TREE / 'packages/apps/Trebuchet/quickstep/AndroidManifest-launcher.xml'
original = manifest.read_text()
home_filter = '''            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.HOME" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.MONKEY"/>
                <category android:name="android.intent.category.LAUNCHER_APP" />
            </intent-filter>'''
if original.count(home_filter) != 1:
    raise SystemExit('Unexpected Quickstep manifest; refusing a broad replacement.')
changed = original.replace(home_filter, '            <!-- Rem product: HOME is provided by com.rem.body. -->')
envsetup = TREE / 'build/make/envsetup.sh'
env_original = envsetup.read_text()
env_before = '''    if (echo -n $1 | grep -q -e "^lineage_") ; then
        LINEAGE_BUILD=$(echo -n $1 | sed -e 's/^lineage_//g')
    else'''
env_after = '''    if (echo -n $1 | grep -q -e "^lineage_") ; then
        LINEAGE_BUILD=$(echo -n $1 | sed -e 's/^lineage_//g')
    elif [ "$1" = "rem_lavender" ]; then
        # Dedicated Rem product inherits the lavender Lineage hardware config.
        LINEAGE_BUILD=lavender
    else'''
if env_original.count(env_before) != 1:
    raise SystemExit('Unexpected Lineage product detection; inspect before changing it.')
shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__'))
manifest.write_text(changed)
envsetup.write_text(env_original.replace(env_before, env_after))
env_patch = subprocess.check_output(['git', 'diff', '--', 'envsetup.sh'], cwd=TREE / 'build/make')
(ROOT / 'evidence/rem-build-product.patch').write_bytes(env_patch)
patch = subprocess.check_output(['git', 'diff', '--', 'quickstep/AndroidManifest-launcher.xml'],
                               cwd=TREE / 'packages/apps/Trebuchet')
(ROOT / 'evidence/rem-quickstep-home.patch').write_bytes(patch)
receipt = {'product': 'rem_lavender-userdebug', 'rem_source_files': {},
           'quickstep_manifest_before_sha256': hashlib.sha256(original.encode()).hexdigest(),
           'quickstep_manifest_after_sha256': hashlib.sha256(changed.encode()).hexdigest(),
           'quickstep_recents_retained': True, 'phone_written': False}
for file in sorted(source.rglob('*')):
    if file.is_file():
        receipt['rem_source_files'][file.relative_to(source).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
(ROOT / 'evidence/rem-product-import.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({'product_imported': True, 'quickstep_home_filter_removed': True,
                  'phone_written': False}))
