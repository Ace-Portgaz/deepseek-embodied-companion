"""Offline character inference. Algorithm adapted from High-Logic/Genie-TTS
(MIT, copyright 2025 High_Logic; see vendor_genie/LICENSE).
Reference-only encoders run offline. No Torch, network, or audio device required.
"""
import json
import os
from pathlib import Path
import time
import numpy as np
import onnxruntime as ort
import soxr
from vendor_genie.Japanese.JapaneseG2P import japanese_to_phones

RATE = 16000

class SynthesisError(RuntimeError):
    pass

class RemGenie:
    def __init__(self, model_dir, threads=2, language=None):
        self.language = language or os.environ.get('REM_VOICE_LANGUAGE', 'zh')
        if self.language not in {'ja', 'zh'}:
            raise ValueError('Unsupported speech language')
        model_dir = Path(model_dir)
        profile_path=model_dir/'profile.json'
        if profile_path.exists():
            profile=json.loads(profile_path.read_text(encoding='utf-8'))
            if profile.get('language')!=self.language:
                raise ValueError('Configured language differs from voice model profile')
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.add_session_config_entry('session.inter_op.allow_spinning', '0')
        options.log_severity_level = 3
        self.chinese_bert = None
        if self.language == 'zh':
            from chinese_bert import ChineseBert
            self.chinese_bert = ChineseBert(model_dir/'chinese-bert',options)
        self.sessions = {}
        for name in ('t2s_encoder', 't2s_first_stage_decoder', 't2s_stage_decoder', 'vits'):
            self.sessions[name] = ort.InferenceSession(str(model_dir/f'{name}_fp32.onnx'),
                sess_options=options, providers=['CPUExecutionProvider'])
        with np.load(model_dir/'reference-features.npz',allow_pickle=False) as data:
            self.reference = {name:data[name] for name in data.files}
        self.decoder_inputs = [x.name for x in self.sessions['t2s_stage_decoder'].get_inputs()]

    def synthesize(self, text, timeout=25):
        if not isinstance(text,str) or not 1 <= len(text.strip()) <= 160:
            raise ValueError('Text must contain 1 to 160 characters')
        start = time.monotonic()
        if self.language == 'zh':
            from vendor_genie.Chinese.ChineseG2P import chinese_to_phones
            normalized, _, phones, word2ph = chinese_to_phones('。'+text.strip())
            bert = self.chinese_bert.features(normalized,word2ph)
        else:
            phones = japanese_to_phones('。'+text.strip())
            bert = np.zeros((len(phones),1024),dtype=np.float32)
        if not phones:
            raise ValueError('No speech phonemes')
        sequence = np.array([phones],dtype=np.int64)
        ref = self.reference
        x, prompts = self.sessions['t2s_encoder'].run(None,dict(
            ref_seq=ref['ref_seq'],ref_bert=ref['ref_bert'],ssl_content=ref['ssl_content'],
            text_seq=sequence,text_bert=bert))
        y, y_emb, *cache = self.sessions['t2s_first_stage_decoder'].run(None,dict(x=x,prompts=prompts))
        # Same autoregressive sequence as Genie; cap generation before 10 seconds
        # of semantics. Timeout is cooperative between ONNX calls.
        stopped = False
        for idx in range(500):
            if time.monotonic()-start > timeout:
                raise SynthesisError('Synthesis deadline exceeded')
            feed = dict(zip(self.decoder_inputs,[y,y_emb,*cache]))
            y,y_emb,stop,*cache = self.sessions['t2s_stage_decoder'].run(None,feed)
            if stop:
                stopped = True
                break
        if not stopped:
            raise SynthesisError('Incomplete semantic sequence')
        if idx < 1:
            raise SynthesisError('Premature semantic stop')
        y[0,-1] = 0
        semantic = np.expand_dims(y[:,-idx:],axis=0)
        eos = np.where(semantic >= 1024)
        if len(eos[0]):
            semantic = semantic[...,:eos[-1][0]]
        if not semantic.size:
            raise SynthesisError('Empty semantic sequence')
        audio = self.sessions['vits'].run(None,dict(text_seq=sequence,
            pred_semantic=semantic,ge=ref['ge'],ge_advanced=ref['ge_advanced']))[0].squeeze()
        if (audio.ndim != 1 or not 0 < len(audio) <= 32000*30 or not np.isfinite(audio).all()
                or time.monotonic()-start > timeout):
            raise SynthesisError('Invalid or late audio')
        audio = soxr.resample(audio,32000,RATE,quality='HQ')
        pcm = (np.clip(audio,-1,1)*32767).astype('<i2').tobytes()
        return pcm, {'complete_seconds':round(time.monotonic()-start,3),
                     'duration_seconds':len(pcm)/(RATE*2),
                     'engine':os.environ.get('REM_VOICE_PROFILE','dafeiyu-zh-sparkle-v1' if self.language=='zh' else 'dafeiyu-ja-genie-v1')}

if __name__ == '__main__':
    import argparse
    import hashlib
    import wave
    import psutil
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--affinity',default='')
    args = parser.parse_args()
    process = psutil.Process()
    if args.affinity:
        process.cpu_affinity([int(x) for x in args.affinity.split(',')])
    out = Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    started = time.monotonic()
    engine = RemGenie(args.model_dir)
    report = {'load_seconds':round(time.monotonic()-started,3),
        'rss_after_load_mib':round(process.memory_info().rss/2**20,1),'samples':[]}
    for name,text in [('wave','はい、今、手を振ってくれましたね。ちゃんと見えていますよ。'),
                      ('gentle','無理はしないでくださいね。少し休んで、お話ししましょう。')]:
        pcm,timing = engine.synthesize(text)
        destination = out/f'rem-{name}-ja.wav'
        with wave.open(str(destination),'wb') as stream:
            stream.setparams((1,2,RATE,0,'NONE','not compressed'))
            stream.writeframes(pcm)
        timing.update(name=name,text=text,path=str(destination),
            rss_mib=round(process.memory_info().rss/2**20,1),
            sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
        report['samples'].append(timing)
        print(json.dumps(timing,ensure_ascii=False),flush=True)
    mem=process.memory_info()
    report['peak_rss_mib']=round(getattr(mem,'peak_wset',mem.rss)/2**20,1)
    report['private_mib']=round(getattr(mem,'private',mem.vms)/2**20,1)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT',json.dumps(report,ensure_ascii=False),flush=True)
