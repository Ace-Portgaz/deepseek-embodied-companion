#!/usr/bin/env python3
"""Repair the dedicated HOME integration and retain lavender's stock overlay action."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
observer = TREE / 'packages/apps/Trebuchet/quickstep/src/com/android/quickstep/OverviewComponentObserver.java'
original = observer.read_text()
changes = [
    ('    private final Intent mFallbackIntent;\n',
     '    private final Intent mFallbackIntent;\n'
     '    private final boolean mHasOwnHome;\n'),
    ('''        ResolveInfo info = context.getPackageManager().resolveActivity(mMyHomeIntent, 0);
        ComponentName myHomeComponent =
                new ComponentName(context.getPackageName(), info.activityInfo.name);
        mMyHomeIntent.setComponent(myHomeComponent);
        mConfigChangesMap.append(myHomeComponent.hashCode(), info.activityInfo.configChanges);
''', '''        ResolveInfo info = context.getPackageManager().resolveActivity(mMyHomeIntent, 0);
        mHasOwnHome = info != null && info.activityInfo != null;
        // A dedicated HOME product keeps Quickstep only for the separate recents UI.
        // Its own HOME intent filter may therefore be absent.
        ComponentName myHomeComponent = mHasOwnHome
                ? new ComponentName(context.getPackageName(), info.activityInfo.name)
                : new ComponentName(mContext, RecentsActivity.class);
        mMyHomeIntent.setComponent(myHomeComponent);
        if (mHasOwnHome) {
            mConfigChangesMap.append(myHomeComponent.hashCode(), info.activityInfo.configChanges);
        }
'''),
    ('        mIsDefaultHome = Objects.equals(mMyHomeIntent.getComponent(), defaultHome);',
     '        mIsDefaultHome = mHasOwnHome\n'
     '                && Objects.equals(mMyHomeIntent.getComponent(), defaultHome);'),
    ('''        if (SEPARATE_RECENTS_ACTIVITY.get()) {
            mIsDefaultHome = false;
            if (defaultHome == null) {''',
     '''        if (SEPARATE_RECENTS_ACTIVITY.get()) {
            mIsDefaultHome = false;
            if (defaultHome == null && mHasOwnHome) {'''),
    ('        if (!mDeviceState.isHomeDisabled() && (defaultHome == null || mIsDefaultHome)) {',
     '        if (mHasOwnHome && !mDeviceState.isHomeDisabled()\n'
     '                && (defaultHome == null || mIsDefaultHome)) {'),
]
if 'private final boolean mHasOwnHome;' not in original:
    changed = original
    for old, new in changes:
        if changed.count(old) != 1:
            raise SystemExit('Unexpected OverviewComponentObserver; refusing broad edits.')
        changed = changed.replace(old, new)
    observer.write_text(changed)

overlay = TREE / 'kernel/xiaomi/sdm660/arch/arm64/boot/dts/qcom/sdm660-mtp-lavender-overlay.dts'
original_overlay = overlay.read_text()
if '&slim_aud' in original_overlay and 'fragment@0' not in original_overlay:
    shorthand = '''// Preserve the overlay action present in lavender's stock DTBO. An empty
// overlay table is not accepted by the boot path observed on this device.
&slim_aud {
    status = "disabled";
};
'''
    if original_overlay.count(shorthand) != 1:
        raise SystemExit('Unexpected existing DTBO repair; inspect manually.')
    original_overlay = original_overlay.replace(shorthand, '')
if 'fragment@0' not in original_overlay:
    if original_overlay.count('F7A overlay') != 1 or '__overlay__' in original_overlay:
        raise SystemExit('Unexpected lavender overlay source; inspect manually.')
    overlay.write_text(original_overlay.rstrip() + '''

// Match the overlay action in the stock DTBO that boots on this device.
// This kernel's dtc requires an explicit fragment for external references.
/ {
    fragment@0 {
        target = <&slim_aud>;
        __overlay__ {
            status = "disabled";
        };
    };
};
''')

dependency_make = ROOT / 'vendor/rem/Android.mk'
if not dependency_make.is_file():
    raise SystemExit('Missing Rem DTBO source dependency rule.')
(TREE / 'vendor/rem/Android.mk').write_bytes(dependency_make.read_bytes())

evidence = ROOT / 'evidence'
for repo, rel, output in [
    ('packages/apps/Trebuchet',
     'quickstep/src/com/android/quickstep/OverviewComponentObserver.java',
     'rem-recents-no-home-fix.patch'),
    ('kernel/xiaomi/sdm660',
     str(overlay.resolve().relative_to((TREE / 'kernel/xiaomi/sdm660').resolve())),
     'lavender-stock-compatible-dtbo.patch'),
]:
    patch = subprocess.check_output(['git', 'diff', '--', rel], cwd=TREE / repo)
    if not patch:
        raise SystemExit('Expected source patch is empty: ' + output)
    (evidence / output).write_bytes(patch)

(evidence / 'first-boot-source-fixes.json').write_text(json.dumps({
    'updated_utc': datetime.now(timezone.utc).isoformat(),
    'recents_fix': 'Handle absent own HOME filter; use separate RecentsActivity without selecting it as HOME',
    'dtbo_fix': 'Restore stock slim_aud disabled overlay action; compare rebuilt DTBO payload against verified stock before use',
    'dtbo_incremental_dependency': 'vendor/rem/Android.mk connects the separate DTBO image to the modified overlay source',
    'validation_pending': ['Incremental build', 'DTBO payload comparison', 'On-device boot and crash-log validation'],
}, indent=2) + '\n')
print('Prepared targeted recents and DTBO source fixes; build and device validation pending.')
