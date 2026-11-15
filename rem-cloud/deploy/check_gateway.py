"""Verify provisioning and WebSocket authentication without speech/LLM calls."""
import asyncio
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_config import load_private


def main():
    settings, credentials = load_private()
    host = settings['public_host']
    device_id = settings['device_id']
    setup_path = f"/setup/{credentials['device_setup_secret']}/xiaozhi/ota/"
    original = json.loads((ROOT / '.private/device-nvs-minimal.json').read_text())
    client_id = next(e['data'] for e in original if (e['namespace'], e['key']) == ('board', 'uuid'))
    headers = {'Device-Id': device_id, 'Client-Id': client_id, 'Content-Type': 'application/json'}
    report = {}
    def post(path, extra):
        req = urllib.request.Request('https://' + host + path,
              data=json.dumps({'application': {'version': '2.2.2.3'}, 'board': {'type': 'lichuang-dev'}}).encode(),
              headers=extra, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as error:
            return error.code, {}
    report['public_ota_hidden'], _ = post('/xiaozhi/ota/', headers)
    report['wrong_device_rejected'], _ = post(setup_path, dict(headers, **{'Device-Id': '00:00:00:00:00:00'}))
    status, data = post(setup_path, headers)
    report['authorized_ota_status'] = status
    if status != 200 or not data.get('websocket', {}).get('token'):
        raise SystemExit('Authorized provisioning check failed')
    ws = data['websocket']
    assert ws['url'] == 'wss://' + host + '/xiaozhi/v1/'
    async def check():
        try:
            async with websockets.connect(ws['url'], additional_headers=headers, open_timeout=10) as rejected:
                message = await asyncio.wait_for(rejected.recv(), 5)
                await asyncio.wait_for(rejected.wait_closed(), 5)
                report['missing_token_rejected'] = message == '认证失败'
        except websockets.exceptions.InvalidStatus as error:
            report['missing_token_rejected'] = error.response.status_code == 401
        auth_headers = dict(headers, Authorization='Bearer ' + ws['token'])
        async with websockets.connect(ws['url'], additional_headers=auth_headers, open_timeout=10) as socket:
            await socket.send(json.dumps({'type':'hello','version':1,'transport':'websocket',
                'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}}))
            reply = json.loads(await asyncio.wait_for(socket.recv(), 12))
            report['authenticated_hello'] = reply.get('type') == 'hello'
    asyncio.run(check())
    (ROOT / 'evidence/gateway-check.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    assert report['public_ota_hidden'] == 404
    assert report['wrong_device_rejected'] == 404
    assert report['missing_token_rejected'] and report['authenticated_hello']


if __name__ == '__main__':
    main()
