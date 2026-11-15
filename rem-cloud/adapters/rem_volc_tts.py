"""Keep upstream streaming/interrupt support; adapt authentication to the new console."""
import asyncio
import uuid
import websockets
from speech_budget import reserve, BudgetExceeded, close_at_limit
from core.providers.tts.huoshan_double_stream import TTSProvider as UpstreamTTS


class TTSProvider(UpstreamTTS):
    async def send_text(self, speaker, text, session_id):
        try:
            reserve(characters=len(text))
        except BudgetExceeded:
            await close_at_limit(self.conn)
            raise
        return await super().send_text(speaker, text, session_id)

    def __init__(self, config, delete_audio_file):
        # Upstream expects access_token for validation; no credential goes in the body.
        cfg = dict(config, access_token=config["api_key"])
        super().__init__(cfg, delete_audio_file)
        self.api_key = config["api_key"]
        self.resource_type = config["resource_id"] in {"seed-tts-2.0", "seed-icl-2.0"}
        self.report_on_last = self.resource_type

    async def _ensure_connection(self):
        if self.ws:
            if self.enable_ws_reuse:
                return self.ws
            await self.finish_connection()
        await self._cancel_monitor_task()
        self.ws = await websockets.connect(
            self.ws_url,
            additional_headers={"X-Api-Key": self.api_key,
                                "X-Api-Resource-Id": self.resource_id,
                                "X-Api-Connect-Id": str(uuid.uuid4())},
            max_size=4_000_000, open_timeout=10, close_timeout=5,
        )
        try:
            await self.start_connection()
            connected = self.parser_response(await asyncio.wait_for(self.ws.recv(), timeout=10))
            if connected.optional.event != 50:  # ConnectionStarted
                raise RuntimeError("Speech connection was rejected")
        except Exception:
            await self.ws.close()
            self.ws = None
            raise
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._start_monitor_tts_response())
        return self.ws
