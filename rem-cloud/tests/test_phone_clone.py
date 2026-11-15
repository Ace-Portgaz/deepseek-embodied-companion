import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phone_clone
import phone_speech
from speech_budget import BudgetExceeded

class CloneTests(unittest.TestCase):
    def response(self,pcm=bytes(3200),**headers):
        response=Mock(status=200)
        values={'X-Rem-Rate':'16000','X-Rem-Engine':'rem-ja-genie-v1',
            'Content-Type':'application/octet-stream','Content-Length':str(len(pcm))}
        values.update(headers)
        response.getheader.side_effect=lambda key,default=None:values.get(key,default)
        response.read.return_value=pcm
        return response

    def test_pcm_contract_and_connection_closed(self):
        conn=Mock();conn.getresponse.return_value=self.response()
        with patch.object(phone_clone,'UnixConnection',return_value=conn):
            audio,timing=phone_clone.synthesize_clone('こんにちは。')
        self.assertEqual(len(audio),3200)
        self.assertEqual(timing['engine'],'rem-ja-genie-v1')
        conn.close.assert_called_once()

    def test_incomplete_oversize_or_wrong_rate_rejected(self):
        for response in [self.response(**{'Content-Length':'3202'}),
            self.response(**{'Content-Length':'960002'}),self.response(**{'X-Rem-Rate':'32000'}),
            self.response(**{'Content-Length':'invalid'}),self.response(pcm=b'\0')]:
            conn=Mock();conn.getresponse.return_value=response
            with self.subTest(response=response),patch.object(phone_clone,'UnixConnection',return_value=conn):
                with self.assertRaises(phone_clone.CloneUnavailable):phone_clone.synthesize_clone('こんにちは。')
            conn.close.assert_called_once()

    def test_clone_does_not_contact_volc_and_reserves_once(self):
        with patch.dict('os.environ',{'REM_PHONE_TTS':'genie'}),patch.object(phone_speech,'reserve') as reserve,\
             patch.object(phone_clone,'synthesize_clone',return_value=(bytes(3200),{})),\
             patch.object(phone_speech.urllib.request,'build_opener') as opener:
            phone_speech.synthesize('fake','こんにちは。','fake')
        reserve.assert_called_once_with(characters=6);opener.assert_not_called()

    def test_fallback_preserves_one_reservation(self):
        response=io.BytesIO(b'data:'+json.dumps({'code':20000000,'data':'AAA='}).encode()+b'\n')
        opener=Mock();opener.open.return_value=response
        with patch.dict('os.environ',{'REM_PHONE_TTS':'genie'}),patch.object(phone_speech,'reserve') as reserve,\
             patch.object(phone_clone,'synthesize_clone',side_effect=phone_clone.CloneUnavailable),\
             patch.object(phone_speech.urllib.request,'build_opener',return_value=opener):
            audio,timing=phone_speech.synthesize('fake','こんにちは。','fake')
        reserve.assert_called_once_with(characters=6)
        self.assertEqual(audio,bytes(2));self.assertEqual(timing['engine'],'volc-vivi')

    def test_limit_blocks_both_providers(self):
        with patch.dict('os.environ',{'REM_PHONE_TTS':'genie'}),\
             patch.object(phone_speech,'reserve',side_effect=BudgetExceeded),\
             patch.object(phone_clone,'synthesize_clone') as clone,\
             patch.object(phone_speech.urllib.request,'build_opener') as opener:
            with self.assertRaises(BudgetExceeded):phone_speech.synthesize('fake','こんにちは。','fake')
        clone.assert_not_called();opener.assert_not_called()

if __name__=='__main__':unittest.main()
