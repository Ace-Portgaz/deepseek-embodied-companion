"""Bounded local CPU feasibility probe, separate from the accepted GPU profile."""
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
os.environ['GENIE_DATA_DIR'] = str(ROOT/'GenieData')
os.environ['Max_Cached_Character_Models'] = '1'
os.environ['Max_Cached_Reference_Audio'] = '1'
sys.path.insert(0, str(ROOT/'Genie-TTS/src'))

import psutil
import numpy as np
import onnxruntime as ort
import soundfile as sf

process = psutil.Process()
if hasattr(process, 'cpu_affinity'):
    process.cpu_affinity(process.cpu_affinity()[:2])
original_session = ort.InferenceSession
def bounded_session(*args, **kwargs):
    options = kwargs.get('sess_options') or ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.add_session_config_entry('session.inter_op.allow_spinning', '0')
    kwargs['sess_options'] = options
    return original_session(*args, **kwargs)
ort.InferenceSession = bounded_session

import genie_tts as genie
from genie_tts.ModelManager import model_manager
from genie_tts.Core.Inference import tts_client
from genie_tts.Utils.Shared import context

OUT = ROOT/'outputs/genie-cpu-preflight'
OUT.mkdir(exist_ok=True, parents=True)
started = time.monotonic()
genie.load_character('rem', ROOT/'models/rem-ja-genie-v1', 'jp')
reference_config = json.loads((ROOT/'reference/reference-config.json').read_text(encoding='utf-8'))
genie.set_reference_audio('rem', Path(reference_config['audio_path']), reference_config['text'])
model = model_manager.get('rem')
assert model is not None and model.PROMPT_ENCODER is not None
reference = context.current_prompt_audio
reference.update_global_emb(model.PROMPT_ENCODER)
assert reference.global_emb is not None
np.savez(ROOT/'models/rem-ja-genie-v1/reference-features.npz',
    ref_seq=reference.phonemes_seq, ref_bert=reference.text_bert,
    ssl_content=reference.ssl_content, ge=reference.global_emb,
    ge_advanced=reference.global_emb_advanced)
# Reference features are immutable for this character. Don't keep reference-only
# encoders resident in a 4 GB server after computing them.
model_manager.cn_hubert = None
model_manager.speaker_verification_model = None
gc.collect()
report = {'engine': 'Genie-TTS ONNX v2ProPlus', 'cpu_threads': 2,
    'affinity': process.cpu_affinity(), 'load_seconds': round(time.monotonic()-started,3),
    'rss_after_load_mib': round(process.memory_info().rss/2**20,1), 'samples':[]}
for name, text in [('wave','はい、今、手を振ってくれましたね。ちゃんと見えていますよ。'),
                   ('gentle','無理はしないでくださいね。少し休んで、お話ししましょう。')]:
    started = time.monotonic()
    audio = tts_client.tts(text, reference, model.T2S_ENCODER,
        model.T2S_FIRST_STAGE_DECODER, model.T2S_STAGE_DECODER, model.VITS,
        model.PROMPT_ENCODER, language=model.LANGUAGE)
    elapsed = time.monotonic()-started
    assert audio is not None
    audio = np.asarray(audio).squeeze()
    assert np.isfinite(audio).all() and audio.ndim == 1 and 0 < len(audio) <= 32000*30
    destination = OUT/f'rem-{name}-ja.wav'
    sf.write(destination, audio, 32000, subtype='PCM_16')
    entry = {'name':name,'text':text,'path':str(destination),'seconds':round(elapsed,3),
        'audio_seconds':len(audio)/32000,'peak':float(np.abs(audio).max()),
        'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'rss_mib':round(process.memory_info().rss/2**20,1)}
    report['samples'].append(entry)
    print(json.dumps(entry,ensure_ascii=False), flush=True)
memory = process.memory_info()
report['peak_rss_mib'] = round(getattr(memory, 'peak_wset', memory.rss)/2**20,1)
report['private_mib'] = round(getattr(memory, 'private', memory.vms)/2**20,1)
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('REPORT',json.dumps(report,ensure_ascii=False),flush=True)
