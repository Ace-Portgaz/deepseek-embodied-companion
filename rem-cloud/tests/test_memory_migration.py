"""Offline migration checks: no cloud access, real credentials or paid APIs."""
import asyncio
import json
from pathlib import Path
import tempfile
import types
import unittest
from test_core import memory


class MemoryMigrationTests(unittest.TestCase):
    def test_enrolled_phone_reads_and_updates_existing_memory_without_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            old = memory.MemoryProvider({"folder": directory})
            old.init_memory("esp-original", None)
            old._path().write_text(json.dumps({"profile": ["紅茶が好き"], "events": []}), encoding="utf-8")
            phone = memory.MemoryProvider({"folder": directory,
                                           "identity_aliases": {"phone-lavender": "esp-original"}})
            llm = types.SimpleNamespace(response_no_stream=lambda *a, **k:
                                       '{"profile":["紅茶が好き"],"events":["新しい端末を使う"]}')
            phone.init_memory("phone-lavender", llm)
            self.assertEqual(phone._path(), old._path())
            self.assertIn("紅茶", asyncio.run(phone.query_memory("好き")))
            asyncio.run(phone.save_memory([types.SimpleNamespace(role="user", content="新しい端末だよ")]))
            self.assertIn("新しい端末", asyncio.run(old.query_memory("端末")))
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)

    def test_unknown_device_keeps_separate_memory(self):
        p = memory.MemoryProvider({"identity_aliases": {"phone": "esp"}})
        p.init_memory("unrelated", None)
        self.assertEqual(p.role_id, "unrelated")

    def test_client_metadata_cannot_choose_another_identity(self):
        p = memory.MemoryProvider({"identity_aliases": {"phone": "esp"}})
        p.init_memory("unrelated", None, identity_aliases={"unrelated": "esp"}, character_id="esp")
        self.assertEqual(p.role_id, "unrelated")

    def test_configuration_is_copied_and_invalid_maps_fail(self):
        aliases = {"phone": "esp"}
        p = memory.MemoryProvider({"identity_aliases": aliases})
        aliases["phone"] = "other"
        p.init_memory("phone", None)
        self.assertEqual(p.role_id, "esp")
        for value in (None, [], {"phone": "phone"}, {"a": "b", "b": "c"},
                      {"a": "b", "b": "a"}, {"*": "esp"}, {"phone": "../private"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                memory.MemoryProvider({"identity_aliases": value})
