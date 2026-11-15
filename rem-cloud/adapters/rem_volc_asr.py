"""Japanese ASR using the vendor's multilingual endpoint and new API-key auth."""
import gzip
import json
import uuid
import asyncio
from speech_budget import reserve, BudgetExceeded, close_at_limit
from core.providers.asr.doubao_stream import ASRProvider as UpstreamASR


class HiddenHeaders(dict):
    def __repr__(self):
        return "<speech authentication headers redacted>"
    __str__ = __repr__


def decode_response(data):
    if not isinstance(data, bytes) or len(data) < 8:
        raise ValueError("Invalid ASR frame")
    header_size = (data[0] & 15) * 4
    kind, flags = data[1] >> 4, data[1] & 15
    serial, compression = data[2] >> 4, data[2] & 15
    if data[0] >> 4 != 1 or header_size < 4 or header_size > len(data):
        raise ValueError("Invalid ASR protocol header")
    pos = header_size
    code = None
    if kind == 15:
        code = int.from_bytes(data[pos:pos + 4], "big")
        pos += 4
    elif flags & 1:
        pos += 4  # sequence number
    if kind not in {9, 15} or len(data) < pos + 4:
        raise ValueError("Unsupported ASR response")
    size = int.from_bytes(data[pos:pos + 4], "big")
    payload = data[pos + 4:]
    if size != len(payload) or size > 4_000_000:
        raise ValueError("Invalid ASR payload size")
    if compression == 1:
        payload = gzip.decompress(payload)
    elif compression != 0:
        raise ValueError("Unsupported ASR compression")
    if serial != 1 or len(payload) > 4_000_000:
        raise ValueError("Unsupported ASR payload")
    body = json.loads(payload)
    result = {"payload_msg": body, "is_last": bool(flags & 2)}
    if code is not None:
        result["code"] = code
    return result


class ASRProvider(UpstreamASR):
    def __init__(self, config, delete_audio_file):
        from character_language import checked
        self.dialogue_language = checked(config.get('language', 'zh-CN'))
        cfg = dict(config, enable_multilingual=True, language=self.dialogue_language)
        super().__init__(cfg, delete_audio_file)
        self.api_key = cfg["api_key"]

    def token_auth(self):
        return HiddenHeaders({"X-Api-Key": self.api_key,
                              "X-Api-Resource-Id": self.resource_id,
                              "X-Api-Request-Id": str(uuid.uuid4())})

    def construct_request(self, reqid):
        return {"user": {"uid": "rem-device"},
                "audio": {"format": "pcm", "codec": "raw", "rate": 16000,
                          "bits": 16, "channel": 1, "language": self.dialogue_language},
                "request": {"model_name": "bigmodel", "enable_itn": True,
                            "enable_punc": True, "show_utterances": True,
                            "result_type": "single", "end_window_size": self.end_window_size}}

    def parse_response(self, data):
        return decode_response(data)

    async def receive_audio(self, conn, pcm_frame, audio_have_voice):
        # Reserve only audio that upstream may actually send to recognition.
        # Idle microphone frames stay local. At session start upstream appends
        # the current frame, sends the last ten, then sends the current one again.
        byte_count = 0
        if audio_have_voice and self.asr_ws is None and not self.is_processing:
            byte_count = len(pcm_frame) + sum(
                len(frame) for frame in (conn.asr_audio + [pcm_frame])[-10:])
        elif self.asr_ws and self.is_processing and not self._is_stopping:
            byte_count = len(pcm_frame)
        try:
            if byte_count:
                reserve(seconds=byte_count / 32000)
        except BudgetExceeded:
            await self.close()
            await close_at_limit(conn)
            return
        await super().receive_audio(conn, pcm_frame, audio_have_voice)
        # Multilingual recognition needs a final packet; waiting only for server text
        # can otherwise leave a short utterance buffered for many seconds.
        if conn.client_voice_stop and self.asr_ws and not self._is_stopping:
            await self._send_stop_request()

    async def _forward_asr_results(self, conn):
        try:
            while self.asr_ws and not conn.stop_event.is_set():
                result = self.parse_response(await asyncio.wait_for(self.asr_ws.recv(), timeout=20))
                if result.get("code", 1000) != 1000:
                    break
                body = result.get("payload_msg", {})
                recognized = body.get("result", {})
                text = recognized.get("text", "")
                stable = any(item.get("definite") for item in recognized.get("utterances", []))
                if text and (stable or result["is_last"]):
                    self.text = text
                    if conn.client_listen_mode != "manual" or conn.client_voice_stop:
                        # Short Japanese responses such as はい must not be discarded
                        # by upstream's 15-frame minimum.
                        await self.handle_voice_stop(conn, conn.asr_audio.copy())
                        break
                if result["is_last"]:
                    break
        except Exception:
            # Transport errors are bounded to this utterance; never log audio/results.
            pass
        finally:
            if self.asr_ws:
                await self.asr_ws.close()
                self.asr_ws = None
            self.is_processing = False
            self._is_stopping = False
            conn.reset_audio_states()
