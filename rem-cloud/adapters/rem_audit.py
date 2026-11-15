"""Connection counters only: no audio, messages, addresses or credentials."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import uuid
from core.websocket_server import WebSocketServer
from core.http_server import SimpleHttpServer
from core.api.ota_handler import OTAHandler
from core.auth import AuthenticationError
from speech_budget import ensure_available, BudgetExceeded

_lock = threading.Lock()


def connection_kind(headers):
    return 'probe' if 'Python' in headers.get('User-Agent', '') else 'device'


def record(stage, headers):
    kind = connection_kind(headers)
    with _lock:
        path = Path('data/connection-status.json')
        try:
            state = json.loads(path.read_text())
        except FileNotFoundError:
            state = {}
        name = kind + '_' + stage
        state[name] = {'count': state.get(name, {}).get('count', 0) + 1,
                       'last_utc': datetime.now(timezone.utc).isoformat()}
        temporary = path.with_suffix('.new')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temporary, path)


class AuditedSocket:
    """Record bounded protocol metadata, never speech, text, or credentials."""
    def __init__(self, websocket):
        self._socket = websocket
        self._started = time.monotonic()
        self._last_saved = 0
        self._id = uuid.uuid4().hex
        self._report = {'kind': connection_kind(websocket.request.headers),
                        'started_utc': datetime.now(timezone.utc).isoformat(),
                        'incoming_packets': 0, 'outgoing_packets': 0,
                        'incoming_bytes': 0, 'outgoing_bytes': 0, 'events': []}

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def save(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_saved < 2:
            return
        self._last_saved = now
        with _lock:
            path = Path('data/dialogue-status.json')
            try:
                reports = json.loads(path.read_text())
            except FileNotFoundError:
                reports = {}
            reports[self._id] = self._report
            reports = dict(list(reports.items())[-12:])
            temporary = path.with_suffix('.new')
            temporary.write_text(json.dumps(reports), encoding='utf-8')
            os.replace(temporary, path)

    def observe(self, message, direction):
        if isinstance(message, (bytes, bytearray, memoryview)):
            self._report[direction + '_packets'] += 1
            self._report[direction + '_bytes'] += len(message)
            key = 'first_' + direction + '_audio_seconds'
            self._report.setdefault(key, round(time.monotonic() - self._started, 3))
            self.save()
            return
        if not isinstance(message, str):
            return
        try:
            payload = json.loads(message)
        except (ValueError, TypeError):
            return
        kind = payload.get('type')
        if kind not in {'hello', 'listen', 'abort', 'tts', 'stt', 'llm'}:
            return
        event = {'direction': direction, 'type': kind,
                 'seconds': round(time.monotonic() - self._started, 3)}
        for key, allowed in [('state', {'start', 'stop', 'detect', 'sentence_start'}),
                             ('mode', {'auto', 'manual', 'realtime'})]:
            if payload.get(key) in allowed:
                event[key] = payload[key]
        if kind == 'hello':
            for key in ('sample_rate', 'frame_duration', 'channels'):
                value = payload.get('audio_params', {}).get(key)
                if isinstance(value, int) and 0 <= value <= 192000:
                    event[key] = value
            version = payload.get('version')
            if isinstance(version, int) and 0 <= version <= 3:
                event['version'] = version
        self._report['events'].append(event)
        self._report['events'] = self._report['events'][-40:]
        self.save(force=True)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        async for message in self._socket:
            self.observe(message, 'incoming')
            yield message

    async def recv(self, *args, **kwargs):
        message = await self._socket.recv(*args, **kwargs)
        self.observe(message, 'incoming')
        return message

    async def send(self, message, *args, **kwargs):
        await self._socket.send(message, *args, **kwargs)
        self.observe(message, 'outgoing')

    async def close(self, *args, **kwargs):
        await self._socket.close(*args, **kwargs)
        self._report['closed_seconds'] = round(time.monotonic() - self._started, 3)
        self._report['close_code'] = self._socket.close_code
        self.save(force=True)


class RemOTAHandler(OTAHandler):
    async def handle_post(self, request):
        response = await super().handle_post(request)
        if 'websocket' in json.loads(response.text):
            record('provisioned', request.headers)
        return response


class RemHttpServer(SimpleHttpServer):
    def __init__(self, config):
        super().__init__(config)
        self.ota_handler = RemOTAHandler(config)


class RemWebSocketServer(WebSocketServer):
    async def _handle_connection(self, websocket):
        from phone_api import persona
        self.config['prompt'] = persona(Path('rem-persona.txt').read_text(encoding='utf-8'))
        audited = AuditedSocket(websocket)
        try:
            await super()._handle_connection(audited)
        finally:
            audited.save(force=True)

    async def _handle_auth(self, websocket):
        await super()._handle_auth(websocket)
        try:
            ensure_available()
        except BudgetExceeded as error:
            raise AuthenticationError('Approved speech allowance reached') from error
        record('authenticated', websocket.request.headers)
