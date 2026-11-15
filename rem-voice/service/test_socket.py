"""Linux integration test for the private socket using a non-neural fake engine."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rem-cloud'))
import phone_clone
from server import make_server

@unittest.skipUnless(hasattr(socket,'AF_UNIX') and sys.platform!='win32','Linux Unix socket test')
class UnixProtocol(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'tts.sock'
        class Engine:
            def synthesize(self,text,timeout=25):return bytes(3200),{}
        self.server=make_server(self.path,Engine())
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.patch=patch.object(phone_clone,'SOCKET',str(self.path));self.patch.start()
    def tearDown(self):
        self.patch.stop();self.server.shutdown();self.server.server_close()
        self.thread.join();self.directory.cleanup()
    def test_valid_pcm_and_busy(self):
        self.assertEqual(len(phone_clone.synthesize_clone('こんにちは。')[0]),3200)
        self.server.busy.acquire()
        try:
            with self.assertRaises(phone_clone.CloneUnavailable):phone_clone.synthesize_clone('はい。')
        finally:self.server.busy.release()
    def test_reject_bad_json_before_engine(self):
        for body in (b'{}',b'[]',json.dumps({'text':'a'*161}).encode(),b'x'*2049):
            connection=phone_clone.UnixConnection('localhost',timeout=2)
            connection.request('POST','/synthesize',body,{'Content-Type':'application/json'})
            response=connection.getresponse()
            self.assertEqual(response.status,400)
            response.read();connection.close()

if __name__=='__main__':unittest.main()
