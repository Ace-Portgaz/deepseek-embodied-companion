"""Private Unix-socket TTS worker. Only the existing rem account can connect."""
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler

MAX_PCM = 16000*2*30

def speak(engine, text, timeout=25):
    if not isinstance(text,str) or not 1 <= len(text.strip()) <= 160:
        raise ValueError('invalid_text')
    # Keep each autoregressive segment below the engine's semantic-token cap.
    sentences = re.findall(r'[^。！？!?\n]+[。！？!?\n]*|[。！？!?\n]+',text.strip())
    pieces = []
    for sentence in sentences:
        for start in range(0,len(sentence),45):
            pieces.append(sentence[start:start+45])
    if not pieces:
        raise ValueError('invalid_text')
    began = time.monotonic()
    result = bytearray()
    for i,piece in enumerate(pieces):
        remaining = timeout-(time.monotonic()-began)
        if remaining <= 0:
            raise TimeoutError('deadline')
        pcm,_ = engine.synthesize(piece, timeout=remaining)
        if not pcm or len(pcm)%2:
            raise ValueError('invalid_audio')
        if i:
            result.extend(bytes(3200))
        result.extend(pcm)
        if len(result)>MAX_PCM or time.monotonic()-began>timeout:
            raise TimeoutError('audio_limit')
    return bytes(result),round(time.monotonic()-began,3)

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    def setup(self):
        self.request.settimeout(4)
        super().setup()
    def log_message(self,*args):
        pass  # Never log generated dialogue, audio, paths, or request headers.
    def answer(self, status, body, content_type='text/plain', extra=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        for key,value in (extra or {}).items():
            self.send_header(key,str(value))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        self.answer(200 if self.path=='/health' else 404,b'ready' if self.path=='/health' else b'not_found')
    def do_POST(self):
        if self.path != '/synthesize':
            self.answer(404,b'not_found'); return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if self.headers.get('Transfer-Encoding') or not 1<=size<=2048:
                raise ValueError('size')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict) or set(data)!={'text'} or not isinstance(data['text'],str) or not 1<=len(data['text'].strip())<=160:
                raise ValueError('text')
        except (ValueError,TypeError,UnicodeError):
            self.answer(400,b'invalid_request'); return
        if not self.server.busy.acquire(blocking=False):
            self.answer(503,b'busy'); return
        try:
            pcm,seconds=speak(self.server.engine,data['text'])
            self.answer(200,pcm,'application/octet-stream',{'X-Rem-Rate':16000,
                'X-Rem-Engine':'rem-ja-genie-v1','X-Rem-Seconds':seconds})
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            self.answer(503,b'synthesis_unavailable')
        finally:
            self.server.busy.release()

def make_server(path,engine):
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads=True
        request_queue_size=4
        def __init__(self):
            self.engine=engine
            self.busy=threading.BoundedSemaphore(1)
            super().__init__(str(path),Handler)
    return Server()

def main():
    from rem_genie import RemGenie
    model_dir=Path(os.environ['REM_VOICE_MODELS'])
    path=Path('/run/rem-voice/tts.sock')
    engine=RemGenie(model_dir)
    # The runtime directory is owned by systemd and dedicated to this service.
    if path.exists():
        if not path.is_socket():
            raise RuntimeError('Unexpected socket path')
        path.unlink()
    os.umask(0o077)
    with make_server(path,engine) as server:
        path.chmod(0o600)
        print('Rem voice ready (private Unix socket)',flush=True)
        server.serve_forever()

if __name__=='__main__':
    main()
