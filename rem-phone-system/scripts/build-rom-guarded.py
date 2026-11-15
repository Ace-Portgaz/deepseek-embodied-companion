#!/usr/bin/env python3
"""Build a local ROM, with physical host-drive guards and an exclusive lock."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TREE = Path(__import__('os').environ.get('REM_ANDROID_TREE', '/home/rembuild/android/lineage'))
EVIDENCE = ROOT / 'evidence'
GIB = 1024 ** 3


def free_space():
    return {drive: round(shutil.disk_usage('/mnt/' + drive.lower()).free / GIB, 2)
            for drive in ('C', 'D')}


def low_space(space, starting=False):
    if space['C'] < (10 if starting else 8): return 'paused_low_system_space'
    if space['D'] < (40 if starting else 35): return 'paused_low_space'
    return None


def save(status):
    status['observed_utc'] = datetime.now(timezone.utc).isoformat()
    target = EVIDENCE / (status.get('record_prefix', 'rom-build') + '-status.json')
    temporary = target.with_suffix('.json.new')
    for attempt in range(5):
        try:
            temporary.write_text(json.dumps(status, indent=2))
            temporary.replace(target)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    print('Status file busy; build and disk protection continue.', flush=True)


def stop_group(process):
    try: os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError: return process.wait()
    # The shell can exit before its compiler children. Check the entire group.
    for _ in range(30):
        process.poll()
        try: os.killpg(process.pid, 0)
        except ProcessLookupError: return process.wait()
        time.sleep(0.5)
    try: os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    return process.wait(timeout=10)


def build():
    target = os.environ.get('REM_BUILD_TARGET', 'bacon')
    if target not in ('bacon', 'RemBody'):
        raise SystemExit('Unsupported build target.')
    prefix = 'rom-build' if target == 'bacon' else 'rem-component-build'
    jobs = int(os.environ.get('REM_BUILD_JOBS', '4'))
    if not 1 <= jobs <= 6:
        raise SystemExit('Build concurrency must be between 1 and 6.')
    status = {'phase': 'preflight', 'product': 'rem_lavender-userdebug',
              'build_target': target, 'record_prefix': prefix,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'jobs': jobs,
              'free_GiB': free_space(), 'full_rom_built': False,
              'phone_written': False, 'workspace': str(TREE),
              'log_path': str(EVIDENCE / (prefix + '.log')),
              'stop_free_GiB': {'C': 8, 'D': 35}}
    reason = low_space(status['free_GiB'], starting=True)
    if reason:
        status['phase'] = reason
        save(status)
        return 1
    command = ['bash', str(ROOT / 'scripts/build-rem.sh')]
    with (EVIDENCE / (prefix + '.log')).open('ab', buffering=0) as log:
        log.write(('\n' + json.dumps({'event': 'build_started', **status}) + '\n').encode())
        process = subprocess.Popen(command, cwd=TREE, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        status['linux_process_group'] = process.pid
        status['phase'] = 'building'
        try:
            while process.poll() is None:
                status['free_GiB'] = free_space()
                save(status)
                reason = low_space(status['free_GiB'])
                if reason:
                    stop_group(process)
                    break
                time.sleep(5)
        except BaseException:
            reason = 'interrupted'
            stop_group(process)
            raise
        finally:
            status['exit_code'] = process.poll()
            status['free_GiB'] = free_space()
            status['phase'] = reason or ('build_complete' if process.returncode == 0 else 'build_failed')
            complete = status['phase'] == 'build_complete'
            status['full_rom_built'] = complete and target == 'bacon'
            status['component_built'] = complete and target == 'RemBody'
            status['artifacts'] = ([str(p) for p in (TREE / 'out/target/product/lavender').glob('lineage-*.zip')]
                                   if target == 'bacon' else
                                   [str(TREE / 'out/target/product/lavender/system/app/RemBody/RemBody.apk')])
            save(status)
    print(json.dumps(status), flush=True)
    return 0 if status['phase'] == 'build_complete' else 1


def main():
    if os.geteuid() == 0: raise SystemExit('Run as rembuild.')
    source = json.loads((EVIDENCE / 'source-sync-status.json').read_text())
    if not source.get('source_tree_complete'): raise SystemExit('Source sync is incomplete.')
    with (TREE / '.rem-source-sync.lock').open('a') as source_lock, \
         (TREE / '.rem-rom-build.lock').open('a') as build_lock:
        try:
            fcntl.flock(source_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(build_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A source sync or ROM build is already running.')
        return build()


if __name__ == '__main__':
    def terminate(signum, frame):
        raise KeyboardInterrupt('Build interrupted.')
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
