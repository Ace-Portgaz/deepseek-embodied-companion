"""One short private-socket probe, charged to the existing shared character cap."""
import sys,json,time,wave
from pathlib import Path
sys.path.insert(0,'/opt/rem-cloud/build/server')
from speech_budget import reserve
from phone_clone import synthesize_clone
text='我看见你挥手啦。今天想聊些什么？'
reserve(characters=len(text))
pcm,timing=synthesize_clone(text)
with wave.open('/var/lib/rem-voice-probe/mandarin.wav','wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
print(json.dumps({'engine':timing['engine'],'seconds':timing['complete_seconds'],'audio_seconds':timing['duration_seconds']}))
