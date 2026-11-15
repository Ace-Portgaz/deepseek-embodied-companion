"""Enforce the approved setup allowance before sending billable speech data."""
import json
import os
from pathlib import Path
import threading
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()
CHINA_TIME = timezone(timedelta(hours=8))


class BudgetExceeded(RuntimeError):
    pass


def _write(path, state):
    temporary = path.with_suffix('.new')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def ensure_available():
    reserve(check_only=True)


def reserve(*, characters=0, seconds=0, check_only=False):
    filename = os.environ.get('REM_TEST_BUDGET_FILE')
    if not filename:
        return
    with _lock:
        path = Path(filename)
        # A missing or malformed ledger must not silently reset the allowance.
        used = json.loads(path.read_text(encoding='utf-8'))
        if used.get('period') == 'day':
            today = datetime.now(CHINA_TIME).date().isoformat()
            if used['date'] < today:
                used = dict(used, date=today, characters=0, seconds=0, paused=False)
        if used.get('paused'):
            raise BudgetExceeded('Approved speech allowance reached')
        new_chars = used['characters'] + characters
        new_seconds = used['seconds'] + seconds
        limits = used.get('limits', {'characters': 200, 'seconds': 60})
        if (new_chars > limits['characters'] or new_seconds > limits['seconds']
                or (check_only and (new_chars >= limits['characters'] or new_seconds >= limits['seconds']))):
            _write(path, dict(used, paused=True))
            raise BudgetExceeded('Approved speech allowance reached')
        updated = dict(used, characters=new_chars, seconds=round(new_seconds, 6))
        _write(path, updated)


async def close_at_limit(conn):
    try:
        await conn.websocket.send(json.dumps({'type': 'stt', 'session_id': conn.session_id,
            'text': '音声の利用上限に達しました。'}))
    finally:
        await conn.websocket.close(code=1008, reason='Approved speech allowance reached')
