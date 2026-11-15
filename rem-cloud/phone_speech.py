# Provider framing adapted from the already verified, bounded verify_speech.py.
import asyncio, base64, gzip, json, os, time, urllib.request, uuid
from speech_budget import reserve
RATE=16000
class SafeFailure(Exception): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def synthesize(key, text, speaker, *, resource_id='seed-tts-2.0', speech_rate=-5, language='zh-CN'):
    from character_language import tts_language
    explicit_language=tts_language(language)
    if not text or len(text) > 160:
        raise SafeFailure("Test text must contain between 1 and 160 characters")
    if resource_id not in {'seed-tts-2.0','seed-icl-2.0'}:
        raise SafeFailure('Unsupported speech resource')
    if type(speech_rate) is not int or not -50<=speech_rate<=100:
        raise SafeFailure('Invalid speech rate')
    reserve(characters=len(text))
    if os.environ.get('REM_PHONE_TTS') == 'genie':
        from phone_clone import synthesize_clone, CloneUnavailable
        try:
            return synthesize_clone(text)
        except CloneUnavailable:
            pass  # One quota reservation covers this attempt and the Vivi fallback.
    body = {"user": {"uid": "rem-smoke-test"}, "req_params": {
        "text": text, "speaker": speaker,
        "audio_params": {"format": "pcm", "sample_rate": RATE, "speech_rate": speech_rate},
        "additions": json.dumps({"explicit_language": explicit_language}),
    }}
    request = urllib.request.Request(
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": key,
                 "X-Api-Resource-Id": resource_id, "X-Api-Request-Id": str(uuid.uuid4())})
    start = time.monotonic()
    pcm, first_audio, complete = bytearray(), None, False
    with urllib.request.build_opener(NoRedirect).open(request, timeout=40) as response:
        for line in response:
            if time.monotonic() - start > 60:
                raise SafeFailure("TTS overall timeout")
            if not line.startswith(b"data:"):
                continue
            item = json.loads(line[5:].strip())
            code = item.get("code", 0)
            if code not in (0, 20000000):
                raise SafeFailure(f"TTS provider error code {int(code)}")
            if item.get("data"):
                if first_audio is None:
                    first_audio = time.monotonic() - start
                pcm.extend(base64.b64decode(item["data"], validate=True))
                if len(pcm) > RATE * 2 * 30:
                    raise SafeFailure("Unexpectedly long generated audio")
            if code == 20000000:
                complete = True
    if not complete or not pcm or len(pcm) % 2:
        raise SafeFailure("TTS did not return a complete PCM stream")
    return bytes(pcm), {"engine": "volc-vivi", "first_audio_seconds": round(first_audio, 3),
                        "complete_seconds": round(time.monotonic() - start, 3),
                        "duration_seconds": round(len(pcm) / RATE / 2, 3)}


def decode_asr(data):
    if not isinstance(data, bytes) or len(data) < 8:
        raise SafeFailure("Invalid ASR frame")
    pos = (data[0] & 15) * 4
    kind, flags = data[1] >> 4, data[1] & 15
    if kind == 15:
        raise SafeFailure(f"ASR provider error code {int.from_bytes(data[pos:pos+4], 'big')}")
    if kind != 9:
        raise SafeFailure("Unexpected ASR message type")
    if flags & 1:
        pos += 4
    size = int.from_bytes(data[pos:pos+4], "big")
    payload = data[pos+4:]
    if size != len(payload) or size > 4_000_000:
        raise SafeFailure("Invalid ASR payload length")
    if data[2] & 15 == 1:
        payload = gzip.decompress(payload)
    return json.loads(payload), bool(flags & 2)


def audio_frame(pcm, final=False):
    payload = gzip.compress(pcm)
    return bytes([0x11, 0x22 if final else 0x20, 0x01, 0x00]) + len(payload).to_bytes(4, "big") + payload


async def recognize(key, pcm, language='zh-CN'):
    from character_language import checked
    checked(language)
    import websockets
    import inspect
    reserve(seconds=len(pcm) / RATE / 2)
    request = {"user": {"uid": "rem-smoke-test"},
               "audio": {"format": "pcm", "codec": "raw", "rate": RATE,
                         "bits": 16, "channel": 1, "language": language},
               "request": {"model_name": "bigmodel", "enable_itn": True,
                           "enable_punc": True, "show_utterances": True}}
    headers = {"X-Api-Key": key, "X-Api-Resource-Id": "volc.seedasr.sauc.duration",
               "X-Api-Request-Id": str(uuid.uuid4())}
    options=dict(additional_headers=headers,max_size=4_000_000,open_timeout=15,close_timeout=5)
    # The deployed 14.2 transport predates the explicit proxy option (15+).
    # Passing it through **kwargs would fail before any recognition data is sent.
    if 'proxy' in inspect.signature(websockets.connect).parameters:options['proxy']=None
    async with websockets.connect("wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",**options) as ws:
        payload = gzip.compress(json.dumps(request).encode())
        await ws.send(bytes([0x11, 0x10, 0x11, 0x00]) + len(payload).to_bytes(4, "big") + payload)
        decode_asr(await asyncio.wait_for(ws.recv(), timeout=15))
        last_sent = [None]

        async def send():
            step = RATE * 2 // 5
            for offset in range(0, len(pcm), step):
                final = offset + step >= len(pcm)
                await ws.send(audio_frame(pcm[offset:offset+step], final))
                if final:
                    last_sent[0] = time.monotonic()
                else:
                    await asyncio.sleep(0.2)

        sender = asyncio.create_task(send())
        text = ""
        try:
            async with asyncio.timeout(55):
                while True:
                    body, final = decode_asr(await ws.recv())
                    text = body.get("result", {}).get("text") or text
                    if final:
                        break
            await sender
        finally:
            if not sender.done():
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
        if not text:
            raise SafeFailure("ASR returned no transcript")
        return {"transcript": text, "after_audio_seconds": round(time.monotonic()-last_sent[0], 3)}

