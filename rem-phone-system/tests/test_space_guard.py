"""Run inside RemBuild; never starts a network fetch or touches actual source files."""
import importlib.util
import fcntl
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('space_guard', Path(__file__).resolve().parents[1] / 'scripts/sync-source-guarded.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def test_temporary_windows_reader_lock_retries_and_keeps_last_valid_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp)
            target = evidence / 'source-sync-status.json'
            target.write_text('{"phase":"old"}')
            original_replace = Path.replace
            attempts = []

            def locked_twice(source, destination):
                attempts.append(source)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(target.read_text())['phase'], 'old')
                    raise PermissionError('Windows reader holds file')
                return original_replace(source, destination)

            with patch.object(guard, 'EVIDENCE', evidence), \
                 patch.object(Path, 'replace', locked_twice), \
                 patch.object(guard.time, 'sleep'):
                self.assertTrue(guard.save({'phase': 'syncing'}))
            self.assertEqual(json.loads(target.read_text())['phase'], 'syncing')

    def test_download_finishes_even_when_progress_file_stays_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, evidence = root / 'work', root / 'evidence'
            (work / '.repo').mkdir(parents=True)
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            evidence.mkdir()
            (root / 'manifests').mkdir()
            (evidence / 'base-source-manifest.xml').write_text('<manifest/>')
            (root / 'manifests/rem-lavender.xml').write_text('<manifest/>')
            marker = root / 'download-finished'
            target = subprocess.Popen([sys.executable, '-c',
                'import time,pathlib,sys; time.sleep(0.1); pathlib.Path(sys.argv[1]).write_text("done")',
                str(marker)], start_new_session=True)
            original_sleep = guard.time.sleep
            try:
                with patch.multiple(guard, WORKSPACE=work, EVIDENCE=evidence), \
                     patch.object(guard, 'available', return_value=300), \
                     patch.object(guard, 'system_available', return_value=20), \
                     patch.object(guard.os, 'geteuid', return_value=1000), \
                     patch.object(guard.subprocess, 'Popen', return_value=target), \
                     patch.object(Path, 'replace', side_effect=PermissionError('busy')), \
                     patch.object(guard.time, 'sleep', side_effect=lambda _: original_sleep(0.01)), \
                     patch.object(guard.sys, 'stderr', io.StringIO()) as errors:
                    self.assertEqual(guard.main(), 0)
                    self.assertEqual(marker.read_text(), 'done')
                    self.assertIn('disk protection continue', errors.getvalue())
            finally:
                if target.poll() is None: target.kill()
                target.wait()

    def test_second_sync_is_refused_without_starting_another_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / '.repo').mkdir()
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            with (work / '.rem-source-sync.lock').open('a') as active:
                fcntl.flock(active, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(guard, 'WORKSPACE', work), \
                     patch.object(guard.os, 'geteuid', return_value=1000), \
                     patch.object(guard.subprocess, 'Popen') as start:
                    with self.assertRaisesRegex(SystemExit, 'already running'):
                        guard.main()
                    start.assert_not_called()

    def test_running_download_stops_when_physical_space_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, evidence = root / 'work', root / 'evidence'
            (work / '.repo').mkdir(parents=True)
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            evidence.mkdir()
            (root / 'manifests').mkdir()
            (evidence / 'base-source-manifest.xml').write_text('<manifest/>')
            (root / 'manifests/rem-lavender.xml').write_text('<manifest/>')
            target = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
            try:
                with patch.multiple(guard, WORKSPACE=work, EVIDENCE=evidence), \
                     patch.object(guard, 'available', side_effect=[45, 45, 34, 34]), \
                     patch.object(guard, 'system_available', return_value=20), \
                     patch.object(guard.os, 'geteuid', return_value=1000), \
                     patch.object(guard.subprocess, 'Popen', return_value=target):
                    self.assertEqual(guard.main(), 1)
                    self.assertIsNotNone(target.poll())
                    state = json.loads((evidence / 'source-sync-status.json').read_text())
                    self.assertEqual(state['phase'], 'paused_low_space')
                    self.assertFalse(state['source_tree_complete'])
            finally:
                if target.poll() is None: target.kill()
                target.wait()

    def test_low_physical_space_prevents_any_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, evidence = root / 'work', root / 'evidence'
            (work / '.repo').mkdir(parents=True)
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            evidence.mkdir()
            (root / 'manifests').mkdir()
            (evidence / 'base-source-manifest.xml').write_text('<manifest/>')
            (root / 'manifests/rem-lavender.xml').write_text('<manifest/>')
            with patch.multiple(guard, WORKSPACE=work, EVIDENCE=evidence), \
                 patch.object(guard, 'available', return_value=39), \
                 patch.object(guard, 'system_available', return_value=20), \
                 patch.object(guard.os, 'geteuid', return_value=1000), \
                 patch.object(guard.subprocess, 'Popen') as start:
                with self.assertRaises(SystemExit):
                    guard.main()
                start.assert_not_called()
                state = json.loads((evidence / 'source-sync-status.json').read_text())
                self.assertEqual(state['phase'], 'paused_low_space')
                self.assertFalse(state['source_tree_complete'])

    def test_c_drive_low_space_prevents_start_even_with_large_d_drive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, evidence = root / 'work', root / 'evidence'
            (work / '.repo').mkdir(parents=True)
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            evidence.mkdir()
            (root / 'manifests').mkdir()
            (evidence / 'base-source-manifest.xml').write_text('<manifest/>')
            (root / 'manifests/rem-lavender.xml').write_text('<manifest/>')
            with patch.multiple(guard, WORKSPACE=work, EVIDENCE=evidence), \
                 patch.object(guard, 'available', return_value=300), \
                 patch.object(guard, 'system_available', return_value=9), \
                 patch.object(guard.os, 'geteuid', return_value=1000), \
                 patch.object(guard.subprocess, 'Popen') as start:
                with self.assertRaises(SystemExit):
                    guard.main()
                start.assert_not_called()
                state = json.loads((evidence / 'source-sync-status.json').read_text())
                self.assertEqual(state['phase'], 'paused_low_system_space')

    def test_c_drive_drop_stops_own_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, evidence = root / 'work', root / 'evidence'
            (work / '.repo').mkdir(parents=True)
            (work / '.repo/manifest.xml').write_text('<manifest/>')
            evidence.mkdir()
            (root / 'manifests').mkdir()
            (evidence / 'base-source-manifest.xml').write_text('<manifest/>')
            (root / 'manifests/rem-lavender.xml').write_text('<manifest/>')
            target = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
            try:
                with patch.multiple(guard, WORKSPACE=work, EVIDENCE=evidence), \
                     patch.object(guard, 'available', return_value=300), \
                     patch.object(guard, 'system_available', side_effect=[11, 11, 7, 7]), \
                     patch.object(guard.os, 'geteuid', return_value=1000), \
                     patch.object(guard.subprocess, 'Popen', return_value=target):
                    self.assertEqual(guard.main(), 1)
                    self.assertIsNotNone(target.poll())
                    state = json.loads((evidence / 'source-sync-status.json').read_text())
                    self.assertEqual(state['phase'], 'paused_low_system_space')
                    self.assertFalse(state['source_tree_complete'])
            finally:
                if target.poll() is None: target.kill()
                target.wait()

    def test_stop_targets_only_the_started_process_group(self):
        target = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        try:
            guard.stop_group(target)
            self.assertIsNotNone(target.poll())
            self.assertIsNone(other.poll())
        finally:
            if target.poll() is None: target.kill()
            if other.poll() is None: other.kill()
            target.wait()
            other.wait()


if __name__ == '__main__':
    unittest.main()
