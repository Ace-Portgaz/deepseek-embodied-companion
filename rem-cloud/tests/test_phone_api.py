"""Exercise the HTTP boundary without sending any paid provider requests."""
import asyncio
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock, AsyncMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import phone_api


class PhoneBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.persona_patch=patch.object(phone_api,'PERSONA',Path(self.temp.name)/'personality.json')
        self.persona_patch.start()
        self.api=phone_api.PhoneAPI({'phone_devices':{'phone-test':{'token_sha256':sha256(b'test-secret').hexdigest()}},
            'ASR':{'RemVolcASR':{'api_key':'fake'}},'TTS':{'RemVolcTTS':{'api_key':'fake','speaker':'test'}},
            'Memory':{'RemMemory':{'identity_aliases':{'phone-test':'canonical'}}}})
        app=web.Application(client_max_size=1000000)
        app.router.add_get('/status',self.api.status)
        app.router.add_route('*','/personality',self.api.personality)
        app.router.add_post('/turn',self.api.turn)
        self.client=TestClient(TestServer(app));await self.client.start_server()
        self.headers={'X-Rem-Device':'phone-test','Authorization':'Bearer test-secret'}

    async def asyncTearDown(self):
        if self.api.pending:await asyncio.gather(*self.api.pending)
        await self.client.close();self.persona_patch.stop();self.temp.cleanup()

    async def test_authenticated_boundary(self):
        for headers in ({},{'X-Rem-Device':'phone-other','Authorization':'Bearer test-secret'},
                        dict(self.headers,Authorization='test-secret'),dict(self.headers,Authorization='Bearer wrong')):
            response=await self.client.get('/status',headers=headers)
            self.assertEqual(response.status,401)
        response=await self.client.get('/status',headers=self.headers)
        self.assertEqual((await response.json())['language'],'ja-JP')

    async def test_persona_roundtrip_and_invalid_payload(self):
        for value in (None,[],{'style':0},{'style':'x'*2001},{'style':'x','memory':'overwrite'}):
            response=await self.client.post('/personality',json=value,headers=self.headers)
            self.assertEqual(response.status,400)
        response=await self.client.post('/personality',json={'style':'温柔且简短'},headers=self.headers)
        self.assertEqual(response.status,200)
        self.assertIn('温柔且简短',phone_api.persona('base'))
        response=await self.client.get('/personality',headers=self.headers)
        self.assertEqual((await response.json())['style'],'温柔且简短')
        await self.client.post('/personality',json={'style':''},headers=self.headers)
        self.assertEqual(phone_api.persona('base'),'base')

    async def test_reject_images_identity_overrides_and_bad_events_before_billing(self):
        base={'id':'test-identifier-1234','text':'こんにちは'}
        values=[None,[],dict(base,image='image'),dict(base,memory_identity='other'),
            dict(base,events=[{'event':'IDENTITY','age_ms':0}]),
            dict(base,events=[{'event':'WAVE','age_ms':True}]),
            dict(base,events=[{'event':'WAVE','age_ms':30001}]),
            dict(base,audio=base64.b64encode(bytes(3200)).decode()),
            dict(base,text='',audio='not base64'),dict(base,text='x'*1001)]
        with patch.object(phone_api,'ensure_available') as budget:
            for value in values:
                response=await self.client.post('/turn',json=value,headers=self.headers)
                self.assertEqual(response.status,400)
            budget.assert_not_called()

    async def test_daily_limit_applies_before_provider(self):
        with patch.object(phone_api,'ensure_available',side_effect=phone_api.BudgetExceeded):
            response=await self.client.post('/turn',json={'id':'test-identifier-1234','text':'こんにちは'},headers=self.headers)
        self.assertEqual(response.status,429)
        self.assertEqual(await response.text(),'daily_speech_limit')

    async def test_turn_events_and_idempotent_retry(self):
        memory=Mock();memory.query_memory=AsyncMock(return_value='{"profile":[],"events":[]}');memory.save_memory=AsyncMock()
        memory_module=types.ModuleType('memory');memory_module.MemoryProvider=Mock(return_value=memory)
        speech=types.ModuleType('phone_speech');speech.recognize=AsyncMock(return_value={'transcript':'こんにちは'})
        speech.synthesize=Mock(return_value=(bytes(3200),{}))
        completion=Mock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='こんにちは。レムです。'))]))
        self.api.llm=types.SimpleNamespace(model_name='fake',client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=completion))))
        payload={'id':'test-identifier-1234','audio':base64.b64encode(bytes(3200)).decode(),'events':[{'event':'WAVE','age_ms':100}]}
        with patch.dict(sys.modules,{'phone_speech':speech,'core.providers.memory.rem_memory.rem_memory':memory_module}),patch.object(phone_api,'ensure_available') as budget,patch.object(Path,'read_text',return_value='base persona'),patch('cloud_config.private_write'):
            first=await self.client.post('/turn',json=payload,headers=self.headers)
            self.assertEqual(first.status,200)
            result=await first.json()
            second=await self.client.post('/turn',json=payload,headers=self.headers)
            self.assertEqual(await second.json(),result)
            self.assertEqual(result['visual_events_received'],1)
            messages=completion.call_args.kwargs['messages']
            self.assertIn('手を振った',messages[-2]['content'])
            self.assertEqual(messages[-1],{'role':'user','content':'こんにちは'})
            speech.recognize.assert_awaited_once();speech.synthesize.assert_called_once();budget.assert_called_once()
            memory.init_memory.assert_called_once_with('phone-test',self.api.llm)
            self.assertEqual(memory_module.MemoryProvider.call_args.args[0]['identity_aliases'],{'phone-test':'canonical'})

if __name__=='__main__':unittest.main()
