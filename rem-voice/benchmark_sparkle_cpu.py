"""Bounded offline benchmark of the accepted Mandarin voice on two CPU cores."""
from pathlib import Path
import json,os,sys,time,wave,threading
import psutil
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'service'))
os.environ['REM_VOICE_PROFILE']='dafeiyu-zh-sparkle-v1'
os.environ['REM_VOICE_LANGUAGE']='zh'
os.environ['TOKENIZERS_PARALLELISM']='false'
process=psutil.Process()
cores=process.cpu_affinity()
process.cpu_affinity(cores[::2][:2])
peak=[0];done=threading.Event()
def monitor():
    while not done.wait(.1):peak[0]=max(peak[0],process.memory_info().rss)
threading.Thread(target=monitor,daemon=True).start()
from rem_genie import RemGenie
from server import speak
out=ROOT/'outputs/dafeiyu-zh';out.mkdir(parents=True,exist_ok=True)
started=time.monotonic();engine=RemGenie(ROOT/'models/dafeiyu-zh-sparkle-runtime-v1',threads=2,language='zh')
report={'load_seconds':round(time.monotonic()-started,3),'cpu_affinity':process.cpu_affinity(),'samples':[]}
for i,text in enumerate(['我看见你挥手啦。','今天想聊些什么？先说好，白米饭可要留我一份。']):
    began=time.monotonic()
    try:
        pcm,seconds=speak(engine,text,timeout=25)
        path=out/f'sparkle-cpu-v1-{i+1}.wav'
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
        report['samples'].append({'text':text,'seconds':seconds,'audio_seconds':len(pcm)/32000,'file':str(path)})
    except Exception as error:
        report['samples'].append({'text':text,'seconds':round(time.monotonic()-began,3),'error':type(error).__name__+': '+str(error)})
    report['rss_mb']=round(process.memory_info().rss/1024**2,1)
    report['peak_rss_mb']=round(peak[0]/1024**2,1)
    (out/'sparkle-cpu-v1-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
done.set()
