"""Regression for the deployed WebSocket 14.2 transport, without network calls."""
import asyncio
import base64
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phone_speech

class SpeechResourceTests(unittest.TestCase):
    def test_clone_requires_explicit_resource_and_keeps_shared_budget(self):
        audio=bytes(3200)
        body=('data:'+json.dumps({'data':base64.b64encode(audio).decode(),'code':0})+'\n'+
              'data:'+json.dumps({'code':20000000})+'\n').encode()
        for resource,rate in (('seed-tts-2.0',-5),('seed-icl-2.0',0)):
            with self.subTest(resource=resource),patch.object(phone_speech.urllib.request,'build_opener') as opener,patch.object(phone_speech,'reserve') as reserve:
                opener.return_value.open.return_value=io.BytesIO(body)
                options={} if resource=='seed-tts-2.0' else {'resource_id':resource,'speech_rate':rate}
                result,_=phone_speech.synthesize('fake','こんにちは','test-speaker',**options)
                request=opener.return_value.open.call_args.args[0]
                self.assertEqual(dict((k.lower(),v) for k,v in request.header_items())['x-api-resource-id'],resource)
                self.assertEqual(json.loads(request.data)['req_params']['audio_params']['speech_rate'],rate)
                self.assertEqual(result,audio);reserve.assert_called_once_with(characters=5)

    def test_bad_configuration_does_not_consume_budget(self):
        with patch.object(phone_speech,'reserve') as reserve,patch.object(phone_speech.urllib.request,'build_opener') as opener:
            for options in ({'resource_id':'unreviewed-resource'},{'speech_rate':101},{'speech_rate':True}):
                with self.assertRaises(phone_speech.SafeFailure):phone_speech.synthesize('fake','こんにちは','test',**options)
            reserve.assert_not_called();opener.assert_not_called()

class SpeechTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognition_with_pre_proxy_websocket_transport(self):
        final_sent=asyncio.Event()
        class Socket:
            received=0
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def send(self,data):
                if data[1]==0x22:final_sent.set()
            async def recv(self):
                self.received+=1
                if self.received>1:await final_sent.wait()
                body=json.dumps({'result':{'text':'こんにちは'}}).encode()
                return bytes([0x11,0x92 if self.received>1 else 0x90,0x10,0])+len(body).to_bytes(4,'big')+body
        def connect(uri,*,additional_headers,max_size,open_timeout,close_timeout,**kwargs):
            # In 14.2 unknown options reach the event loop and raise TypeError.
            self.assertEqual(kwargs,{})
            self.assertTrue(uri.startswith('wss://openspeech.bytedance.com/'))
            return Socket()
        with patch.dict(sys.modules,{'websockets':types.SimpleNamespace(connect=connect)}),patch.object(phone_speech,'reserve') as reserve:
            result=await phone_speech.recognize('fake',bytes(3200))
        self.assertEqual(result['transcript'],'こんにちは')
        reserve.assert_called_once_with(seconds=.1)

if __name__=='__main__':unittest.main()
