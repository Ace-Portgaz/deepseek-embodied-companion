import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('romguard', Path(__file__).resolve().parents[1] / 'scripts/build-rom-guarded.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class BuildGuardTests(unittest.TestCase):
    def test_component_build_preserves_full_rom_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            original = '{"phase":"build_complete","full_rom_built":true}'
            (work / 'rom-build-status.json').write_text(original)
            complete = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
            complete.wait()
            with patch.multiple(guard, EVIDENCE=work, TREE=work), \
                 patch.dict(os.environ, {'REM_BUILD_TARGET': 'RemBody'}), \
                 patch.object(guard, 'free_space', return_value={'C':20,'D':200}), \
                 patch.object(guard.subprocess, 'Popen', return_value=complete):
                self.assertEqual(guard.build(), 0)
            self.assertEqual((work / 'rom-build-status.json').read_text(), original)
            status = json.loads((work / 'rem-component-build-status.json').read_text())
            self.assertTrue(status['component_built'])
            self.assertFalse(status['full_rom_built'])
            self.assertTrue(status['artifacts'][0].endswith('/RemBody/RemBody.apk'))

    def test_low_drive_prevents_build(self):
        for drives in ({'C': 9, 'D': 200}, {'C': 20, 'D': 39}):
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(guard, 'EVIDENCE', Path(tmp)), \
                 patch.object(guard, 'free_space', return_value=drives), \
                 patch.object(guard.subprocess, 'Popen') as launch:
                self.assertEqual(guard.build(), 1)
                launch.assert_not_called()

    def test_running_build_stops_on_either_drive_without_stopping_other_work(self):
        for low in ({'C': 7, 'D': 200}, {'C': 20, 'D': 34}):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                own = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
                other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
                try:
                    with patch.multiple(guard, EVIDENCE=work, TREE=work), \
                         patch.object(guard, 'free_space', side_effect=[{'C':20,'D':200}, low, low]), \
                         patch.object(guard.subprocess, 'Popen', return_value=own):
                        self.assertEqual(guard.build(), 1)
                    self.assertIsNotNone(own.poll())
                    self.assertIsNone(other.poll())
                    self.assertFalse(json.loads((work/'rom-build-status.json').read_text())['full_rom_built'])
                finally:
                    for process in (own, other):
                        if process.poll() is None: process.kill()
                        process.wait()


if __name__ == '__main__': unittest.main()
