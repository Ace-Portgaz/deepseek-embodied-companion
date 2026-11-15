"""Install the reviewed first-boot repair, with separate explicit device phases.

Run on Windows. Does not unlock, format, relock, or reboot the phone.
The Recovery menu must be used to leave sideload and finally reboot.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ADB = Path(__import__('os').environ.get('ADB', 'adb'))
EVIDENCE = ROOT / 'evidence'
ARTIFACTS = ROOT / 'out/first-boot-fix-20261114'
PREFIX = 'first-boot-fix'
STOCK_DTBO = 'b0873a9f96908b88461ba1fadca2c3011e60f30432339bcdae1fc37679381bd9'
FIRST_REPAIR_DTBO = '6790e7f02901f9cc03d921ba3b9511c92d28025a69011f94b422b537fa702150'
CAMERA_CONFIGS = {
    'etc/camera/lavender_s5kgm1_ofilm_i_chromatix.xml': 'a9f0ea890317c73abb6caa1cac9f2c7d9f0c5a34ffd036288dea966b96e7c374',
    'etc/camera/lavender_s5kgm1_sunny_ii_chromatix.xml': '0cf49b69e7bf6a90d20e69d6654ef5db9760c1816eab3ddeff864351f8e30ca7',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def adb(*args, binary=False, timeout=30):
    p = subprocess.run([str(ADB), '-d', *args], capture_output=True, timeout=timeout)
    if p.returncode:
        raise SystemExit('ADB command failed: ' + p.stderr.decode(errors='replace').strip())
    return p.stdout if binary else p.stdout.decode(errors='replace').strip()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def device(expected_state):
    listing = subprocess.check_output([str(ADB), 'devices'], text=True, timeout=10)
    rows = [line.split() for line in listing.splitlines()[1:] if line.strip()]
    if len(rows) != 1 or rows[0][1] != expected_state:
        raise SystemExit('Expected one device in ' + expected_state + ' mode.')
    return hashlib.sha256(rows[0][0].encode()).hexdigest()


def save(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def gate():
    identity = device('recovery')
    model = adb('shell', 'getprop ro.product.device')
    if model != 'lavender' or adb('shell', 'id -u') != '0':
        raise SystemExit('Unexpected device or Recovery permissions.')
    if adb('shell', 'getprop ro.boot.verifiedbootstate') != 'orange':
        raise SystemExit('Boot state is not the expected unlocked engineering state.')
    battery = int(adb('shell', 'cat /sys/class/power_supply/battery/capacity'))
    if battery < 30:
        raise SystemExit('Charge the phone before installation.')
    save(PREFIX + '-device-gate.json', {
        'verified_utc': now(), 'usb_identity_sha256': identity,
        'product': model, 'adb_mode': 'recovery', 'root': True,
        'verified_boot_state': 'orange', 'battery_percent': battery,
        'authorization': 'first-system-user-authorization.json',
    })
    print('Recovery device gate passed for lavender; no partitions written.')


def reviewed(mode):
    gate_data = json.loads((EVIDENCE / (PREFIX + '-device-gate.json')).read_text())
    if device(mode) != gate_data['usb_identity_sha256']:
        raise SystemExit('USB device differs from the checked phone.')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(gate_data['verified_utc'])).total_seconds()
    if not 0 <= age <= 6 * 3600:
        raise SystemExit('Device gate expired; check Recovery again.')
    manifest = json.loads((ARTIFACTS / 'artifact-manifest.json').read_text())
    required = ('dtbo_payload_matches_boot_tested_stock', 'ota_startup_images_match_target_files',
                'engineering_build', 'keep_bootloader_unlocked')
    if manifest['device'] != 'lavender' or not all(manifest[k] for k in required):
        raise SystemExit('Artifact review is incomplete.')
    if manifest['ota_zip_crc'] != 'passed' or manifest['avb_integrity'] != 'passed_with_embedded_test_keys':
        raise SystemExit('Artifact integrity did not pass.')
    if PREFIX == 'camera-fix':
        if manifest.get('repair') != PREFIX or {
                item['relative_path']: item['sha256'] for item in manifest.get('vendor_files', [])
                } != CAMERA_CONFIGS:
            raise SystemExit('Reviewed paired camera configurations are missing.')
    expected = {item['name']: item for item in manifest['exports']}
    return manifest, expected


def sideload():
    manifest, expected = reviewed('sideload')
    package = ARTIFACTS / manifest['package']
    if digest(package) != expected[package.name]['sha256']:
        raise SystemExit('Reviewed OTA package changed.')
    result = {'started_utc': now(), 'package': package.name,
              'package_sha256': expected[package.name]['sha256'], 'phone_formatted': False}
    with (EVIDENCE / (PREFIX + '-sideload.log')).open('wb') as log:
        p = subprocess.run([str(ADB), '-d', 'sideload', str(package)],
                           stdout=log, stderr=subprocess.STDOUT, timeout=900)
    result.update({'finished_utc': now(), 'host_exit_code': p.returncode,
                   'recovery_install_verification_pending': True})
    save(PREFIX + '-install.json', result)
    if p.returncode:
        raise SystemExit('Sideload failed; inspect its log and Recovery screen.')
    print('Sideload host transfer completed. Recovery install result still needs verification.')


def finish():
    manifest, expected = reviewed('recovery')
    if adb('shell', 'getprop ro.product.device') != 'lavender' or adb('shell', 'id -u') != '0':
        raise SystemExit('Unexpected Recovery runtime.')
    last_install = adb('shell', 'cat /tmp/last_install')
    lines = last_install.splitlines()
    if len(lines) < 2 or lines[0] != '/sideload/package.zip' or lines[1] != '1':
        raise SystemExit('Recovery has not reported a successful sideload installation.')
    for name in ('boot.img', 'vbmeta.img'):
        part = name.removesuffix('.img')
        raw = adb('exec-out', 'head', '-c', str(expected[name]['bytes']),
                  '/dev/block/bootdevice/by-name/' + part, binary=True, timeout=90)
        if hashlib.sha256(raw).hexdigest() != expected[name]['sha256']:
            raise SystemExit('Installed OTA image does not match: ' + part)
    mountpoint = '/mnt/rem-fixed-system-check'
    adb('shell', 'mkdir -p ' + mountpoint)
    adb('shell', 'mount -t ext4 -o ro,noload /dev/block/bootdevice/by-name/system ' + mountpoint)
    try:
        for apk in manifest['system_apks']:
            path = mountpoint + '/system/' + apk['relative_path']
            if adb('shell', 'sha256sum ' + path).split()[0] != apk['sha256']:
                raise SystemExit('Installed system application differs from the repair: ' + apk['relative_path'])
    finally:
        adb('shell', 'umount ' + mountpoint)
    if manifest.get('vendor_files'):
        mountpoint = '/mnt/rem-fixed-vendor-check'
        adb('shell', 'mkdir -p ' + mountpoint)
        adb('shell', 'mount -t ext4 -o ro,noload /dev/block/bootdevice/by-name/vendor ' + mountpoint)
        try:
            for config in manifest['vendor_files']:
                path = mountpoint + '/' + config['relative_path']
                if adb('shell', 'sha256sum ' + path).split()[0] != config['sha256']:
                    raise SystemExit('Installed vendor configuration differs: ' + config['relative_path'])
        finally:
            adb('shell', 'umount ' + mountpoint)
    dtbo = ARTIFACTS / 'dtbo.img'
    wanted = expected['dtbo.img']['sha256']
    if digest(dtbo) != wanted:
        raise SystemExit('Reviewed DTBO changed.')
    partition = '/dev/block/bootdevice/by-name/dtbo'
    if int(adb('shell', 'blockdev --getsize64 ' + partition)) != expected['dtbo.img']['bytes']:
        raise SystemExit('Unexpected DTBO partition capacity.')
    before = adb('shell', 'sha256sum ' + partition).split()[0]
    allowed_previous = {STOCK_DTBO, wanted}
    if PREFIX == 'camera-fix':
        previous = json.loads((EVIDENCE / 'first-boot-fix-install.json').read_text())
        if previous.get('dtbo_readback_verified') and previous.get('installed_dtbo_sha256') == FIRST_REPAIR_DTBO:
            allowed_previous.add(FIRST_REPAIR_DTBO)
    if before not in allowed_previous:
        raise SystemExit('Current DTBO differs from known verified predecessors; inspect before writing.')
    if before != wanted:
        adb('push', str(dtbo), '/tmp/rem-fixed-dtbo.img', timeout=90)
        if adb('shell', 'sha256sum /tmp/rem-fixed-dtbo.img').split()[0] != wanted:
            raise SystemExit('DTBO transfer checksum mismatch.')
        adb('shell', 'dd if=/tmp/rem-fixed-dtbo.img of=' + partition + ' bs=4096 && sync', timeout=90)
        if adb('shell', 'sha256sum ' + partition).split()[0] != wanted:
            raise SystemExit('DTBO partition readback mismatch. Stay in Recovery.')
    receipt = json.loads((EVIDENCE / (PREFIX + '-install.json')).read_text())
    receipt.update({'verified_utc': now(), 'recovery_install_verification_pending': False,
                    'recovery_install_success': True, 'installed_boot_and_vbmeta_match_ota': True,
                    'installed_rem_and_trebuchet_apks_verified': True,
                    'installed_vendor_files_verified': manifest.get('vendor_files', []),
                    'installed_dtbo_sha256': wanted, 'dtbo_readback_verified': True,
                    'android_boot_verification_pending': True,
                    'reboot_instruction': 'Use Recovery main menu Reboot system now'})
    save(PREFIX + '-install.json', receipt)
    (EVIDENCE / (PREFIX + '-last-install.txt')).write_text(last_install + '\n', encoding='utf-8')
    print('Recovery install success and startup image readbacks verified. Use the Recovery menu to reboot.')


if __name__ == '__main__':
    actions = {'gate': gate, 'sideload': sideload, 'finish': finish}
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=list(actions))
    parser.add_argument('--repair', choices=['first-boot', 'camera'], default='first-boot')
    args = parser.parse_args()
    PREFIX = args.repair + '-fix'
    ARTIFACTS = ROOT / ('out/' + PREFIX + '-20261114')
    actions[args.action]()
