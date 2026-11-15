import json
import math
import os
from pathlib import Path
import re

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent
report_path = ROOT / 'outputs/trial-report.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
model = WhisperModel(str(ROOT / 'cache/whisper-small'), device='cpu', compute_type='int8', cpu_threads=6)
rows = []
for sample in report['samples']:
    audio, sr = sf.read(sample['file'], dtype='float32')
    divisor = math.gcd(sr, 16000)
    pcm = resample_poly(audio, 16000 // divisor, sr // divisor).astype(np.float32)
    segments, _ = model.transcribe(pcm, language='ja', beam_size=5, condition_on_previous_text=False)
    text = ''.join(s.text for s in segments)
    row = {'file': sample['file'], 'expected': sample['text'], 'asr': text,
           'rms': float(np.sqrt(np.mean(audio * audio))),
           'peak': float(np.abs(audio).max()),
           'clipped_samples': int(np.sum(np.abs(audio) >= 0.9999))}
    rows.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
(ROOT / 'outputs/audio-check.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
