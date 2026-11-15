import asyncio
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_config import build_config, load_private, validate, with_device_secrets


def load_adapter(filename, dependency, base_name, base):
    previous = sys.modules.get(dependency)
    stub = types.ModuleType(dependency)
    setattr(stub, base_name, base)
    sys.modules[dependency] = stub
    try:
        spec = importlib.util.spec_from_file_location("test_" + filename, ROOT / "adapters" / (filename + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            del sys.modules[dependency]
        else:
            sys.modules[dependency] = previous


class BaseMemory:
    def __init__(self, config):
        self.config = config
        self.role_id = None
    def init_memory(self, role_id, llm, **kwargs):
        self.role_id, self.llm = role_id, llm


memory = load_adapter("rem_memory", "core.providers.memory.base", "MemoryProviderBase", BaseMemory)
asr = load_adapter("rem_volc_asr", "core.providers.asr.doubao_stream", "ASRProvider", object)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((ROOT / "settings.example.json").read_text())
        self.settings.update(public_host="companion.example.com", device_id="aa:bb:cc:dd:ee:ff", tts_speaker="test-only")
        self.keys = with_device_secrets({"deepseek_api_key": "fake-ds", "volc_asr_api_key": "fake-asr", "volc_tts_api_key": "fake-tts"})
    def test_default_is_not_runnable_without_keys_and_voice(self):
        self.assertIn("deepseek_api_key", validate({}, {}))
        self.assertIn("tts_speaker", validate({}, {}))
    def test_remote_security_and_selected_providers(self):
        cfg = build_config(self.settings, self.keys, "日本語")
        self.assertEqual(cfg["server"]["auth"]["allowed_devices"], [])
        self.assertTrue(cfg["server"]["auth"]["enabled"])
        self.assertTrue(cfg["server"]["websocket"].startswith("wss://"))
        self.assertEqual(cfg["selected_module"]["LLM"], "RemDeepSeek")
        self.assertEqual(cfg["ASR"]["RemVolcASR"]["language"], "zh-CN")
        self.assertEqual(cfg["TTS"]["RemVolcTTS"]["additions"]["explicit_language"], "zh-cn")
    def test_untrusted_configuration_cannot_inject_caddy_environment(self):
        self.settings["public_host"] = "companion.example.com\nOTHER=bad"
        self.assertTrue(validate(self.settings, self.keys))
        self.settings["public_host"] = "companion.example.com"
        self.settings["device_id"] = "*"
        self.assertTrue(validate(self.settings, self.keys))
    def test_tokens_are_stable_across_saves(self):
        self.assertEqual(with_device_secrets(self.keys), self.keys)
        self.assertNotEqual(self.keys["device_setup_secret"], self.keys["server_auth_key"])
    def test_public_ip_uses_verified_tls_and_retains_device_auth(self):
        self.settings["public_host"] = "1.1.1.1"
        cfg = build_config(self.settings, self.keys, "日本語")
        self.assertEqual(cfg["server"]["websocket"], "wss://1.1.1.1/xiaozhi/v1/")
        self.assertTrue(cfg["server"]["auth"]["enabled"])
    def test_invalid_or_private_ip_cannot_be_used_as_public_endpoint(self):
        for host in ("127.0.0.1", "10.0.0.16", "0.0.0.0", "224.0.0.1", "1.1.1.1:443", "https://1.1.1.1", "1.1.1.1\nX=bad"):
            self.settings["public_host"] = host
            with self.subTest(host=host):
                self.assertTrue(validate(self.settings, self.keys))
    def test_plain_deepseek_key_does_not_enable_paid_voice_by_accident(self):
        self.keys.pop("volc_tts_api_key")
        with self.assertRaises(ValueError):
            build_config(self.settings, self.keys, "日本語")
    def test_config_reader_does_not_generate_or_write_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "settings.example.json").write_text("{}")
            self.assertEqual(load_private(directory), ({}, {}))
            self.assertFalse((Path(directory) / ".private").exists())
    def test_memory_aliases_are_explicit_server_settings_only(self):
        cfg = build_config(self.settings, self.keys, "日本語")
        self.assertEqual(cfg["Memory"]["RemMemory"]["identity_aliases"], {})
        self.settings["memory_identity_aliases"] = {"enrolled-phone": "existing-device"}
        cfg = build_config(self.settings, self.keys, "日本語")
        self.assertEqual(cfg["Memory"]["RemMemory"]["identity_aliases"], self.settings["memory_identity_aliases"])


class ProtocolTests(unittest.TestCase):
    def packet(self, body, compressed=True, flags=1):
        payload = json.dumps(body, ensure_ascii=False).encode()
        if compressed:
            payload = gzip.compress(payload)
        header = bytes([0x11, 0x90 | flags, 0x10 | int(compressed), 0])
        return header + ((1).to_bytes(4, "big") if flags & 1 else b"") + len(payload).to_bytes(4, "big") + payload
    def test_compressed_final_frame_with_negative_sequence(self):
        decoded = asr.decode_response(self.packet({"result": {"text": "はい"}}, flags=3))
        self.assertTrue(decoded["is_last"])
        self.assertEqual(decoded["payload_msg"]["result"]["text"], "はい")
    def test_no_sequence_and_plain_json(self):
        self.assertEqual(asr.decode_response(self.packet({"result": {}}, False, 0))["payload_msg"], {"result": {}})
    def test_rejects_truncated_or_unknown_frames(self):
        with self.assertRaises(ValueError):
            asr.decode_response(self.packet({"result": {}})[:-2])
        with self.assertRaises(ValueError):
            asr.decode_response(b"invalid")
    def test_credentials_not_exposed_in_header_repr(self):
        headers = asr.HiddenHeaders({"X-Api-Key": "private-test-key"})
        self.assertNotIn("private-test-key", str(headers))
        self.assertEqual(headers["X-Api-Key"], "private-test-key")
    def test_request_is_japanese_and_has_no_secret_in_body(self):
        provider = object.__new__(asr.ASRProvider)
        provider.end_window_size = 600
        provider.dialogue_language = 'ja-JP'
        payload = provider.construct_request("request-test")
        self.assertEqual(payload["audio"]["language"], "ja-JP")
        self.assertEqual(payload["request"]["model_name"], "bigmodel")
        self.assertNotIn("app", payload)

    def test_chinese_request_uses_mandarin(self):
        provider = object.__new__(asr.ASRProvider)
        provider.end_window_size = 600
        provider.dialogue_language = 'zh-CN'
        self.assertEqual(provider.construct_request('test')['audio']['language'],'zh-CN')


class MemoryTests(unittest.TestCase):
    def test_schema_limits_and_basic_secret_filter(self):
        cleaned = memory.clean_memory({"profile": ["好きなのは紅茶", "sk-testsecretvalue123", "x@example.com"],
                                       "events": [f"出来事{i}" for i in range(50)]})
        self.assertEqual(cleaned["profile"], ["好きなのは紅茶"])
        self.assertEqual(len(cleaned["events"]), 32)
    def test_memory_survives_restart_and_invalid_reply_does_not_erase(self):
        with tempfile.TemporaryDirectory() as directory:
            class FakeLLM:
                response = '{"profile":["呼び名はハル"],"events":["プログラムが動いた"]}'
                def response_no_stream(self, *args, **kwargs):
                    return self.response
            llm = FakeLLM()
            first = memory.MemoryProvider({"folder": directory})
            first.init_memory("device-a", llm)
            msgs = [types.SimpleNamespace(role="user", content="ハルと呼んで")]
            asyncio.run(first.save_memory(msgs))
            restarted = memory.MemoryProvider({"folder": directory})
            restarted.init_memory("device-a", llm)
            before = asyncio.run(restarted.query_memory("プログラム"))
            self.assertIn("ハル", before)
            llm.response = "not JSON"
            asyncio.run(restarted.save_memory(msgs))
            self.assertEqual(asyncio.run(restarted.query_memory("プログラム")), before)
            other = memory.MemoryProvider({"folder": directory})
            other.init_memory("device-b", llm)
            self.assertNotIn("ハル", asyncio.run(other.query_memory("プログラム")))
    def test_summary_only_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = types.SimpleNamespace(response_no_stream=lambda *a, **k: '{"profile":[],"events":["紅茶が好き"]}')
            provider = memory.MemoryProvider({"folder": directory})
            provider.init_memory("device-a", llm)
            asyncio.run(provider.save_memory([types.SimpleNamespace(role="user", content="RAW_PRIVATE_TEST_SENTENCE")]))
            saved = next(Path(directory).glob("*.json")).read_text(encoding="utf-8")
            self.assertNotIn("RAW_PRIVATE_TEST_SENTENCE", saved)
    def test_relevant_event_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = memory.MemoryProvider({"folder": directory})
            provider.init_memory("device-a", None)
            provider._path().write_text(json.dumps({"profile": [], "events": ["紅茶が好き"] + [f"出来事{i}" for i in range(15)]}), encoding="utf-8")
            response = json.loads(asyncio.run(provider.query_memory("紅茶")))
            self.assertEqual(response["events"][0], "紅茶が好き")
            self.assertEqual(len(response["events"]), 6)


class SpeechLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognition_budget_excludes_idle_audio_and_includes_preroll(self):
        class FakeUpstream:
            async def receive_audio(self, conn, pcm, voiced):
                pass
        adapter = load_adapter('rem_volc_asr', 'core.providers.asr.doubao_stream', 'ASRProvider', FakeUpstream)
        provider = object.__new__(adapter.ASRProvider)
        provider.asr_ws = None
        provider.is_processing = False
        provider._is_stopping = False
        conn = types.SimpleNamespace(asr_audio=[b'x' * 3200] * 12, client_voice_stop=False)
        with patch.object(adapter, 'reserve') as reserve:
            await provider.receive_audio(conn, b'x' * 1920, False)
            reserve.assert_not_called()
            await provider.receive_audio(conn, b'x' * 1920, True)
            reserve.assert_called_once_with(seconds=(9 * 3200 + 2 * 1920) / 32000)
        provider.asr_ws = object()
        provider.is_processing = True
        with patch.object(adapter, 'reserve') as reserve:
            await provider.receive_audio(conn, b'x' * 1920, False)
            reserve.assert_called_once_with(seconds=.06)

    async def test_short_japanese_response_is_not_dropped(self):
        frame = ProtocolTests().packet({"result": {"text": "はい", "utterances": [{"text": "はい", "definite": True}]}}, flags=3)
        class Socket:
            closed = False
            async def recv(self):
                return frame
            async def close(self):
                self.closed = True
        socket = Socket()
        provider = object.__new__(asr.ASRProvider)
        provider.asr_ws = socket
        provider.is_processing = True
        provider._is_stopping = False
        processed = []
        async def on_stop(conn, audio):
            processed.append((provider.text, audio))
        provider.handle_voice_stop = on_stop
        connection = types.SimpleNamespace(stop_event=threading.Event(), asr_audio=[b"short"],
                                           client_listen_mode="auto", client_voice_stop=True,
                                           reset_audio_states=lambda: None)
        await provider._forward_asr_results(connection)
        self.assertEqual(processed, [("はい", [b"short"])])
        self.assertTrue(socket.closed)
        self.assertFalse(provider.is_processing)

    async def test_non_final_hypothesis_does_not_trigger_reply(self):
        frames = [ProtocolTests().packet({"result": {"text": "あ", "utterances": [{"definite": False}]}}, flags=1),
                  ProtocolTests().packet({"result": {"text": "ありがとう", "utterances": [{"definite": True}]}}, flags=3)]
        class Socket:
            async def recv(self):
                return frames.pop(0)
            async def close(self):
                pass
        provider = object.__new__(asr.ASRProvider)
        provider.asr_ws = Socket()
        processed = []
        async def on_stop(conn, audio):
            processed.append(provider.text)
        provider.handle_voice_stop = on_stop
        connection = types.SimpleNamespace(stop_event=threading.Event(), asr_audio=[b"pcm"],
                                           client_listen_mode="manual", client_voice_stop=True,
                                           reset_audio_states=lambda: None)
        await provider._forward_asr_results(connection)
        self.assertEqual(processed, ["ありがとう"])


if __name__ == "__main__":
    unittest.main()
