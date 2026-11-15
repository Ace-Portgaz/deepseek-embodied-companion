#!/usr/bin/env python3
"""Resume the source tree, pausing before either host drive fills.

Uses a separate process group so stopping affects this sync and its children only.
No file deletion, phone access, cloud credentials, or automatic purchases.
"""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

WORKSPACE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
EVIDENCE = Path(__file__).resolve().parents[1] / 'evidence'
RESERVE_GIB = 30
STOP_GIB = 35  # Allow room for writes completing after the stop signal.
START_GIB = 40
SYSTEM_START_GIB = 10
SYSTEM_STOP_GIB = 8


def available():
    return shutil.disk_usage('/mnt/d').free / (1024 ** 3)


def system_available():
    return shutil.disk_usage('/mnt/c').free / (1024 ** 3)


def save(status):
    status['observed_utc'] = datetime.now(timezone.utc).isoformat()
    temp = EVIDENCE / 'source-sync-status.json.new'
    # Windows readers can briefly deny renaming a file on the shared D drive.
    # Status publishing is optional; disk checks must keep running if it fails.
    for attempt in range(5):
        try:
            temp.write_text(json.dumps(status, indent=2), encoding='utf-8')
            temp.replace(EVIDENCE / 'source-sync-status.json')
            return True
        except PermissionError:
            if attempt < 4:
                time.sleep(0.05 * (attempt + 1))
    print('Progress file is temporarily busy; source sync and disk protection continue.',
          file=sys.stderr, flush=True)
    return False


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return process.wait(timeout=10)


def main():
    if os.geteuid() == 0:
        raise SystemExit('Run as rembuild, not root.')
    if not (WORKSPACE / '.repo/manifest.xml').exists():
        raise SystemExit('Initialize and inspect the source manifest first.')
    # Keep the lock on the Linux filesystem, outside repo-managed directories.
    with (WORKSPACE / '.rem-source-sync.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A source sync is already running; duplicate start refused.')
        return run_sync()


def run_sync():
    projects = []
    for source in (EVIDENCE / 'base-source-manifest.xml',
                   EVIDENCE.parent / 'manifests/rem-lavender.xml'):
        for project in ET.parse(source).getroot().findall('project'):
            path = WORKSPACE / project.attrib.get('path', project.attrib['name'])
            if not path.resolve().is_relative_to(WORKSPACE):
                raise SystemExit('Invalid project path.')
            projects.append(path)
    status = {'phase': 'preflight', 'source_tree_complete': False,
              'projects_total': len(projects), 'host_free_GiB': round(available(), 1),
              'system_C_free_GiB': round(system_available(), 1),
              'system_C_stop_threshold_GiB': SYSTEM_STOP_GIB,
              'reserve_GiB': RESERVE_GIB, 'stop_threshold_GiB': STOP_GIB,
              'workspace': str(WORKSPACE), 'full_rom_built': False}
    if available() < START_GIB:
        status['phase'] = 'paused_low_space'
        save(status)
        raise SystemExit('Insufficient space to start safely.')
    if system_available() < SYSTEM_START_GIB:
        status['phase'] = 'paused_low_system_space'
        save(status)
        raise SystemExit('C drive is below the safe start margin.')
    command = ['/home/rembuild/bin/repo', 'sync', '--current-branch', '--jobs=4',
               '--retry-fetches=5', '--no-clone-bundle', '--no-tags']
    # Let other projects complete if one server connection fails. Repo retries
    # transient fetch errors with backoff, and still returns failure if needed.
    status['command'] = command
    status['network_fetch_attempts'] = 5
    status['stop_all_on_first_network_error'] = False
    with (EVIDENCE / 'source-sync.log').open('ab') as log:
        log.write((json.dumps({'event': 'sync_started',
                               'utc': datetime.now(timezone.utc).isoformat(),
                               'command': command}) + '\n').encode('utf-8'))
        log.flush()
        process = subprocess.Popen(command, cwd=WORKSPACE, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        status['phase'] = 'syncing'
        status['linux_process_group'] = process.pid
        reason = None
        try:
            while process.poll() is None:
                free = available()
                system_free = system_available()
                status['host_free_GiB'] = round(free, 1)
                status['system_C_free_GiB'] = round(system_free, 1)
                status['projects_with_checkout_metadata'] = sum((p / '.git').exists() for p in projects)
                save(status)
                if free < STOP_GIB:
                    reason = 'paused_low_space'
                    stop_group(process)
                    break
                if system_free < SYSTEM_STOP_GIB:
                    reason = 'paused_low_system_space'
                    stop_group(process)
                    break
                time.sleep(5)
        except BaseException:
            reason = 'interrupted'
            stop_group(process)
            raise
        finally:
            status['exit_code'] = process.poll()
            status['host_free_GiB'] = round(available(), 1)
            status['system_C_free_GiB'] = round(system_available(), 1)
            status['phase'] = reason or ('sync_complete' if process.returncode == 0 else 'sync_failed')
            status['source_tree_complete'] = status['phase'] == 'sync_complete'
            save(status)
    print(json.dumps(status))
    return 0 if status['source_tree_complete'] else 1


if __name__ == '__main__':
    def terminate(signum, frame):
        raise KeyboardInterrupt('Source sync received a stop signal.')
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
