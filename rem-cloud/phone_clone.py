"""Private same-host voice transport. No credential or network destination input."""
import http.client
import json
import socket
import time
import os
import re

SOCKET = '/run/rem-voice/tts.sock'
MAX_PCM = 16000*2*30

class CloneUnavailable(RuntimeError):
    pass

class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)

def synthesize_clone(text):
    if not isinstance(text,str) or not 1<=len(text.strip())<=160:
        raise ValueError('invalid_text')
    profile=os.environ.get('REM_VOICE_PROFILE','dafeiyu-zh-sparkle-v1')
    if not re.fullmatch('[a-z0-9-]{1,80}',profile):
        raise CloneUnavailable('invalid_profile')
    started=time.monotonic()
    connection=UnixConnection('localhost',timeout=28)
    try:
        connection.request('POST','/synthesize',json.dumps({'text':text}).encode(),
            {'Content-Type':'application/json'})
        response=connection.getresponse()
        if (response.status!=200 or response.getheader('X-Rem-Rate')!='16000'
                or response.getheader('X-Rem-Engine')!=profile
                or response.getheader('Content-Type')!='application/octet-stream'):
            raise CloneUnavailable('clone_response')
        size=int(response.getheader('Content-Length','0'))
        if not 1<=size<=MAX_PCM or size%2:
            raise CloneUnavailable('clone_size')
        pcm=response.read(MAX_PCM+1)
        if len(pcm)!=size or time.monotonic()-started>29:
            raise CloneUnavailable('clone_incomplete')
        return pcm,{'engine':profile,'complete_seconds':round(time.monotonic()-started,3),
                    'duration_seconds':len(pcm)/32000}
    except (OSError,http.client.HTTPException,ValueError) as error:
        raise CloneUnavailable('clone_unavailable') from error
    finally:
        connection.close()
