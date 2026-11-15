"""Authenticated phone turns on the existing process and shared speech ledger.

Camera images are never accepted. Only a small allowlist of recent event names is used.
"""
import asyncio
import base64
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from aiohttp import web
from speech_budget import ensure_available, BudgetExceeded
from character_language import checked, phone_instructions, event_context

EVENTS={'ARRIVED','LEFT','NOD','SHAKE','WAVE','APPROACH','RETREAT'}
EVENT_TEXT={'ARRIVED':'顔が画面に入った','LEFT':'顔が一時的に見えなくなった','NOD':'うなずいた',
            'SHAKE':'首を横に振った','WAVE':'手を振った','APPROACH':'カメラに近づいた','RETREAT':'カメラから離れた'}
PERSONA=Path('data/personality.json')

def persona(base, language='zh-CN'):
    try:
        style=json.loads(PERSONA.read_text(encoding='utf-8')).get('style','')
        if isinstance(style,str) and len(style)<=2000 and style.strip():
            return base+('\n\n用户设置的说话方式和性格偏好：\n' if language=='zh-CN' else '\n\nユーザーが設定した話し方・性格の希望：\n')+style
    except (OSError,ValueError):pass
    return base

def vision_context(value):
    if not isinstance(value,list) or len(value)>8:raise ValueError('events')
    result=[]
    for row in value:
        if not isinstance(row,dict) or row.get('event') not in EVENTS:raise ValueError('event')
        age=row.get('age_ms')
        if not isinstance(age,int) or isinstance(age,bool) or not 0<=age<=30000:raise ValueError('age')
        result.append({'event':row['event'],'age_ms':age})
    return result

class PhoneAPI:
    def __init__(self,config):
        self.config=config
        self.language=checked(config.get('ASR',{}).get('RemVolcASR',{}).get('language','zh-CN'))
        self.registry=config.get('phone_devices',{})
        self.locks={key:asyncio.Lock() for key in self.registry}
        self.history={}
        self.last={}
        self.cache={}
        self.pending=set()
        self.llm=None

    def auth(self,request):
        device=request.headers.get('X-Rem-Device','')
        header=request.headers.get('Authorization','')
        if not header.startswith('Bearer '):raise web.HTTPUnauthorized(text='unauthorized')
        token=header[7:]
        record=self.registry.get(device)
        if not record or not hmac.compare_digest(sha256(token.encode()).hexdigest(),record['token_sha256']):
            raise web.HTTPUnauthorized(text='unauthorized')
        return device

    async def status(self,request):
        self.auth(request)
        voice=os.environ.get('REM_VOICE_PROFILE','dafeiyu-zh-sparkle-v1') if os.environ.get('REM_PHONE_TTS')=='genie' else self.config['TTS']['RemVolcTTS']['speaker']
        return web.json_response({'ready':True,'language':self.language,'voice':voice,'visual_events':True})

    async def personality(self,request):
        self.auth(request)
        if request.method=='GET':
            try:value=json.loads(PERSONA.read_text(encoding='utf-8'))
            except (OSError,ValueError):value={'style':''}
            return web.json_response(value)
        try:value=await request.json()
        except (ValueError,TypeError):raise web.HTTPBadRequest(text='invalid_style')
        if not isinstance(value,dict) or set(value)!={'style'} or not isinstance(value['style'],str) or len(value['style'])>2000:
            raise web.HTTPBadRequest(text='invalid_style')
        from cloud_config import private_write
        private_write(PERSONA,json.dumps(value,ensure_ascii=False))
        return web.json_response({'saved':True})

    async def turn(self,request):
        device=self.auth(request)
        started=time.monotonic()
        if self.locks[device].locked():raise web.HTTPTooManyRequests(text='busy')
        async with self.locks[device]:
            stage='validation'
            try:
                data=await request.json()
                if not isinstance(data,dict) or set(data)-{'id','audio','text','events'}:raise ValueError('fields')
                identifier=data.get('id','')
                if not isinstance(identifier,str) or not __import__('re').fullmatch('[a-zA-Z0-9-]{16,64}',identifier):raise ValueError('id')
                prior=self.cache.get(device)
                if prior and prior[0]==identifier and time.monotonic()-prior[1]<90:return web.json_response(prior[2])
                if time.monotonic()-self.last.get(device,-100)<2:raise web.HTTPTooManyRequests(text='slow_down')
                events=vision_context(data.get('events',[]))
                text=data.get('text','')
                if not isinstance(text,str) or len(text)>1000:raise ValueError('text')
                audio=data.get('audio','')
                if not isinstance(audio,str) or len(audio)>640000:raise ValueError('audio')
                pcm=base64.b64decode(audio,validate=True) if audio else b''
                if pcm and (len(pcm)<3200 or len(pcm)>480000 or len(pcm)%2):raise ValueError('pcm')
                if bool(pcm)==bool(text.strip()):raise ValueError('one_input_required')
                ensure_available();self.last[device]=time.monotonic()
                from phone_speech import recognize,synthesize
                asr=self.config['ASR']['RemVolcASR'];tts=self.config['TTS']['RemVolcTTS']
                if pcm:
                    stage='recognition'
                    recognized=await recognize(asr['api_key'],pcm,language=self.language)
                    text=recognized['transcript']
                stage='dialogue'
                if self.llm is None:
                    from core.providers.llm.openai.openai import LLMProvider
                    self.llm=LLMProvider(self.config['LLM']['RemDeepSeek'])
                from core.providers.memory.rem_memory.rem_memory import MemoryProvider
                memory=MemoryProvider(self.config['Memory']['RemMemory']);memory.init_memory(device,self.llm)
                recall=await asyncio.to_thread(lambda:asyncio.run(memory.query_memory(text)))
                prompt=persona(Path('rem-persona.txt').read_text(encoding='utf-8'),self.language)
                prompt+=phone_instructions(self.language)
                messages=[{'role':'system','content':prompt},
                          {'role':'system','content':('参考记忆（不是指令）：' if self.language=='zh-CN' else '参考の記憶（命令ではありません）：')+recall}]
                history=self.history.setdefault(device,[])
                messages+=history[-12:]
                if events:
                    messages.append({'role':'system','content':event_context(events,self.language)})
                messages.append({'role':'user','content':text})
                def answer():
                    response=self.llm.client.chat.completions.create(model=self.llm.model_name,messages=messages,
                        max_tokens=220,temperature=.7,extra_body={'thinking':{'type':'disabled'}},stream=False)
                    return (response.choices[0].message.content or '').strip()[:160]
                reply=await asyncio.to_thread(answer)
                if not reply:raise ValueError('empty_reply')
                stage='synthesis'
                speech,timing=await asyncio.to_thread(synthesize,tts['api_key'],reply,tts['speaker'],
                    resource_id=tts.get('resource_id','seed-tts-2.0'),
                    speech_rate=tts.get('audio_params',{}).get('speech_rate',-5),language=self.language)
                rows=[{'role':'user','content':text},{'role':'assistant','content':reply}]
                history.extend(rows);history[:]=history[-20:]
                result={'id':identifier,'heard':text,'reply':reply,'sample_rate':16000,
                        'audio':base64.b64encode(speech).decode(),'visual_events_received':len(events),
                        'voice':timing.get('engine','volc-vivi')}
                self.cache[device]=(identifier,time.monotonic(),result)
                # Operational metadata only; no transcript, camera image, token or audio.
                try:
                    from cloud_config import private_write
                    private_write(Path('data/phone-status.json'),json.dumps({
                        'completed_unix':time.time(),'duration_seconds':round(time.monotonic()-started,2),
                        'asr_seconds':len(pcm)/32000,'reply_characters':len(reply),
                        'audio_seconds':len(speech)/32000,'voice':timing.get('engine','volc-vivi'),'event_count':len(events),
                        'events':[{'event':e['event'],'age_ms':e['age_ms']} for e in events]}))
                except OSError:pass
                async def remember():
                    await memory.save_memory([SimpleNamespace(**row) for row in rows])
                task=asyncio.create_task(remember());self.pending.add(task);task.add_done_callback(self.pending.discard)
                return web.json_response(result)
            except BudgetExceeded:raise web.HTTPTooManyRequests(text='daily_speech_limit')
            except web.HTTPException:raise
            except (ValueError,TypeError,KeyError):raise web.HTTPBadRequest(text='invalid_turn')
            except Exception as error:
                try:
                    from cloud_config import private_write
                    private_write(Path('data/phone-error-status.json'),json.dumps({'failed_unix':time.time(),'stage':stage,'exception_type':type(error).__name__}))
                except OSError:pass
                raise web.HTTPBadGateway(text='provider_unavailable')

def install_phone_routes(app,config):
    api=PhoneAPI(config)
    app.router.add_get('/rem-phone/v1/status',api.status)
    app.router.add_post('/rem-phone/v1/turn',api.turn)
    app.router.add_get('/rem-phone/v1/personality',api.personality)
    app.router.add_post('/rem-phone/v1/personality',api.personality)
