"""Reject mismatched phone/artifacts/configs before any DTBO write."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'repair_installer', Path(__file__).resolve().parents[1] / 'scripts/install-first-boot-fix.py')
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class CameraInstallGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patches = [patch.object(INSTALLER, 'EVIDENCE', self.root),
                        patch.object(INSTALLER, 'ARTIFACTS', self.root),
                        patch.object(INSTALLER, 'PREFIX', 'camera-fix'),
                        patch.object(INSTALLER, 'device', return_value='same-phone')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.gate = {'usb_identity_sha256': 'same-phone',
                     'verified_utc': datetime.now(timezone.utc).isoformat()}
        self.manifest = {
            'device': 'lavender', 'repair': 'camera-fix',
            'dtbo_payload_matches_boot_tested_stock': True,
            'ota_startup_images_match_target_files': True,
            'engineering_build': True, 'keep_bootloader_unlocked': True,
            'ota_zip_crc': 'passed', 'avb_integrity': 'passed_with_embedded_test_keys',
            'exports': [], 'system_apks': [],
            'vendor_files': [{'relative_path': k, 'sha256': v}
                             for k, v in INSTALLER.CAMERA_CONFIGS.items()],
        }
        self.write_inputs()

    def write_inputs(self):
        (self.root / 'camera-fix-device-gate.json').write_text(json.dumps(self.gate))
        (self.root / 'artifact-manifest.json').write_text(json.dumps(self.manifest))

    def test_valid_review_is_accepted(self):
        actual, _ = INSTALLER.reviewed('recovery')
        self.assertEqual(actual['vendor_files'], self.manifest['vendor_files'])

    def test_other_usb_device_is_rejected(self):
        with patch.object(INSTALLER, 'device', return_value='other-phone'):
            with self.assertRaisesRegex(SystemExit, 'USB device differs'):
                INSTALLER.reviewed('recovery')

    def test_expired_device_check_is_rejected(self):
        self.gate['verified_utc'] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        self.write_inputs()
        with self.assertRaisesRegex(SystemExit, 'expired'):
            INSTALLER.reviewed('recovery')

    def test_wrong_camera_config_is_rejected(self):
        self.manifest['vendor_files'][0]['sha256'] = 'unreviewed-configuration'
        self.write_inputs()
        with self.assertRaisesRegex(SystemExit, 'camera configurations are missing'):
            INSTALLER.reviewed('sideload')

    def test_other_repair_package_is_rejected(self):
        self.manifest['repair'] = 'first-boot-fix'
        self.write_inputs()
        with self.assertRaisesRegex(SystemExit, 'camera configurations are missing'):
            INSTALLER.reviewed('sideload')

    def test_installed_vendor_mismatch_stops_before_dtbo_write(self):
        import hashlib
        raw = b'mocked installed image'
        expected = {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                    for name in ('boot.img', 'vbmeta.img')}
        calls = []

        def fake_adb(*args, **kwargs):
            calls.append(args)
            if args == ('shell', 'getprop ro.product.device'):
                return 'lavender'
            if args == ('shell', 'id -u'):
                return '0'
            if args == ('shell', 'cat /tmp/last_install'):
                return '/sideload/package.zip\n1\n'
            if args[0] == 'exec-out':
                return raw
            if args[0] == 'shell' and args[1].startswith('sha256sum '):
                return 'wrong-installed-file  file'
            return ''

        with patch.object(INSTALLER, 'reviewed', return_value=(self.manifest, expected)), \
                patch.object(INSTALLER, 'adb', side_effect=fake_adb):
            with self.assertRaisesRegex(SystemExit, 'Installed vendor configuration differs'):
                INSTALLER.finish()
        self.assertIn(('shell', 'umount /mnt/rem-fixed-vendor-check'), calls)
        self.assertFalse(any('dd if=' in ' '.join(args) or args[0] == 'push' for args in calls))


if __name__ == '__main__':
    unittest.main()
