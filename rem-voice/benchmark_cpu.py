"""Local CPU-only capacity probe. Does not emulate the cloud server CPU or OS."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT / 'GPT-SoVITS-v2Pro'
parser = argparse.ArgumentParser()
parser.add_argument('--japanese-only', action='store_true')
args = parser.parse_args()
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['MKL_NUM_THREADS'] = '2'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['language'] = 'en_US'
os.chdir(REPO)
sys.path[:0] = [str(REPO), str(REPO / 'GPT_SoVITS')]

import psutil

process = psutil.Process()
allowed = process.cpu_affinity()
affinity = [allowed[0], allowed[min(2, len(allowed) - 1)]]
process.cpu_affinity(affinity)
peak = {'rss_bytes': 0, 'private_bytes': 0}
stop = threading.Event()


def sample_memory():
    while not stop.wait(0.1):
        mem = process.memory_info()
        peak['rss_bytes'] = max(peak['rss_bytes'], mem.rss)
        peak['private_bytes'] = max(peak['private_bytes'], getattr(mem, 'private', 0))


threading.Thread(target=sample_memory, daemon=True).start()
import numpy as np
import soundfile as sf
import torch
from TTS_infer_pack.TTS import TTS, TTS_Config


class JapaneseOnlyTTS(TTS):
    """all_ja uses zero BERT features upstream, so the Chinese BERT is unused."""

    def init_bert_weights(self, base_path):
        self.bert_model = None
        self.bert_tokenizer = None

    def run(self, inputs):
        if inputs.get('text_lang') != 'all_ja' or inputs.get('prompt_lang') != 'all_ja':
            raise ValueError('Japanese-only optimization requires all_ja for text and reference')
        return super().run(inputs)

torch.set_num_threads(2)
torch.set_num_interop_threads(1)
ref = json.loads((ROOT / 'reference/reference-config.json').read_text(encoding='utf-8'))
weights = REPO / 'GPT_SoVITS/pretrained_models'
settings = {'custom': {
    'device': 'cpu', 'is_half': False, 'version': 'v2ProPlus',
    'bert_base_path': str(weights / 'chinese-roberta-wwm-ext-large'),
    'cnhuhbert_base_path': str(weights / 'chinese-hubert-base'),
    't2s_weights_path': str(weights / 's1v3.ckpt'),
    'vits_weights_path': str(weights / 'v2Pro/s2Gv2ProPlus.pth'),
}}
started = time.monotonic()
pipeline_class = JapaneseOnlyTTS if args.japanese_only else TTS
output_dir = ROOT / ('outputs/cpu-preflight-ja-only' if args.japanese_only else 'outputs/cpu-preflight')
output_dir.mkdir(exist_ok=True)
config = TTS_Config(settings)
config.configs_path = str(output_dir / 'runtime-config.yaml')
pipeline = pipeline_class(config)
load_seconds = time.monotonic() - started
print('CPU_MODEL_READY', round(load_seconds, 3), flush=True)
samples = [
    ('warmup', 'はい、今、手を振ってくれましたね。ちゃんと見えていますよ。'),
    ('warm_wave', 'はい、今、手を振ってくれましたね。ちゃんと見えていますよ。'),
    ('warm_gentle', '無理はしないでくださいね。少し休んで、お話ししましょう。'),
]
rows = []
for name, text in samples:
    start = time.monotonic()
    chunks = list(pipeline.run({
        'text': text, 'text_lang': 'all_ja', 'ref_audio_path': ref['audio_path'],
        'prompt_text': ref['text'], 'prompt_lang': 'all_ja',
        'top_k': 5, 'top_p': 1, 'temperature': 0.8,
        'text_split_method': 'cut3', 'batch_size': 1, 'speed_factor': 1.0,
        'seed': 42, 'parallel_infer': True, 'repetition_penalty': 1.35,
        'return_fragment': False,
    }))
    elapsed = time.monotonic() - start
    rates = {rate for rate, _ in chunks}
    if len(rates) != 1:
        raise RuntimeError('Invalid synthesis output')
    sr = chunks[0][0]
    audio = np.concatenate([x for _, x in chunks])
    if not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio.astype(float))) == 0:
        raise RuntimeError('Empty or invalid synthesis')
    path = output_dir / f'{name}.wav'
    sf.write(str(path), audio, sr, subtype='PCM_16')
    row = {'name': name, 'text': text, 'file': str(path),
           'generation_seconds': elapsed, 'audio_seconds': len(audio) / sr,
           'rtf': elapsed / (len(audio) / sr)}
    rows.append(row)
    print('CPU_SAMPLE', json.dumps(row, ensure_ascii=False), flush=True)
stop.set()
report = {
    'scope': 'Local Windows Ryzen 9 8945HS CPU probe, NOT a cloud server benchmark',
    'device': 'cpu', 'precision': 'float32', 'cpu_threads': 2,
    'unused_chinese_bert_omitted': args.japanese_only,
    'logical_processor_affinity': affinity, 'model_load_seconds': load_seconds,
    'peak_memory': peak, 'samples': rows, 'paid_api_calls': 0,
    'production_phone_changed': False, 'production_cloud_changed': False,
    'limitations': ['No 4 GB hard memory cap', 'Cloud CPU and Linux runtime differ',
                    'Does not include ASR/DeepSeek/network time or concurrent server workload'],
}
(output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('CPU_PROBE_COMPLETE', json.dumps(peak), flush=True)
