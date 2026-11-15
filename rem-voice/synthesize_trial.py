"""Offline GPT-SoVITS v2ProPlus audition using the reviewed local reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT / 'GPT-SoVITS-v2Pro'
os.environ.setdefault('HF_HOME', str(ROOT / 'cache/huggingface'))
os.environ.setdefault('TORCH_HOME', str(ROOT / 'cache/torch'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / 'cache/numba'))
os.environ.setdefault('NLTK_DATA', str(ROOT / 'cache/nltk_data'))
os.environ['PATH'] = str(ROOT / 'bin') + os.pathsep + os.environ.get('PATH', '')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['G2PW'] = '0'
os.environ['language'] = 'en_US'
os.chdir(REPO)
sys.path[:0] = [str(REPO), str(REPO / 'GPT_SoVITS')]

parser = argparse.ArgumentParser()
parser.add_argument('--reference', default=str(ROOT / 'reference/reference-config.json'))
parser.add_argument('--text', default=None)
parser.add_argument('--output', default=None)
args = parser.parse_args()

import numpy as np
import soundfile as sf
import torch
from TTS_infer_pack.TTS import TTS, TTS_Config

if not torch.cuda.is_available():
    raise RuntimeError('GPU not available; refusing unexpectedly slow CPU trial')
torch.set_num_threads(6)
ref = json.loads(Path(args.reference).read_text(encoding='utf-8'))
weights = REPO / 'GPT_SoVITS/pretrained_models'
settings = {'custom': {
    'device': 'cuda', 'is_half': True, 'version': 'v2ProPlus',
    'bert_base_path': str(weights / 'chinese-roberta-wwm-ext-large'),
    'cnhuhbert_base_path': str(weights / 'chinese-hubert-base'),
    't2s_weights_path': str(weights / 's1v3.ckpt'),
    'vits_weights_path': str(weights / 'v2Pro/s2Gv2ProPlus.pth'),
}}
started = time.monotonic()
pipeline = TTS(TTS_Config(settings))
loaded = time.monotonic() - started
print('MODEL_READY', round(loaded, 2), 'seconds', flush=True)
samples = [(args.output or 'rem-custom.wav', args.text)] if args.text else [
    ('rem-greeting-ja.wav', 'おかえりなさい。今日もお疲れさまでした。レムは、あなたのそばにいます。'),
    ('rem-wave-ja.wav', 'はい、今、手を振ってくれましたね。ちゃんと見えていますよ。'),
    ('rem-gentle-ja.wav', '無理はしないでくださいね。少し休んで、お話ししましょう。'),
]
(ROOT / 'outputs').mkdir(parents=True, exist_ok=True)
results = []
for filename, text in samples:
    begin = time.monotonic()
    chunks = list(pipeline.run({
        'text': text, 'text_lang': 'all_ja',
        'ref_audio_path': ref['audio_path'], 'prompt_text': ref['text'],
        'prompt_lang': 'all_ja', 'top_k': 5, 'top_p': 1,
        'temperature': 0.8, 'text_split_method': 'cut3', 'batch_size': 1,
        'speed_factor': 1.0, 'seed': 42, 'parallel_infer': True,
        'repetition_penalty': 1.35, 'return_fragment': False,
    }))
    if not chunks or len({rate for rate, _ in chunks}) != 1:
        raise RuntimeError('Invalid synthesis output')
    rate = chunks[0][0]
    audio = np.concatenate([chunk for _, chunk in chunks])
    if audio.size == 0 or not np.isfinite(audio).all() or np.max(np.abs(audio.astype(float))) == 0:
        raise RuntimeError('Empty or invalid audio')
    output = ROOT / 'outputs' / filename
    sf.write(str(output), audio, rate, subtype='PCM_16')
    elapsed = time.monotonic() - begin
    duration = len(audio) / rate
    with output.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    result = {'file': str(output), 'text': text, 'sample_rate': rate,
              'duration_seconds': duration, 'generation_seconds': elapsed,
              'rtf': elapsed / duration, 'sha256': digest}
    results.append(result)
    print('SAMPLE_COMPLETE', json.dumps(result, ensure_ascii=False), flush=True)
report = {'engine': 'GPT-SoVITS', 'version': 'v2ProPlus',
          'source_tag': '20250606v2pro', 'source_commit': 'd7c2210da8c013e81a94bfc7b811a477c99fd506',
          'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__,
          'text_split_method': 'cut3', 'seed': 42, 'temperature': 0.8,
          'model_load_seconds': loaded, 'reference': ref,
          'peak_allocated_vram_bytes': torch.cuda.max_memory_allocated(),
          'samples': results, 'production_phone_changed': False,
          'production_cloud_changed': False, 'paid_api_calls': 0}
(ROOT / 'outputs/trial-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('TRIAL_COMPLETE', flush=True)
