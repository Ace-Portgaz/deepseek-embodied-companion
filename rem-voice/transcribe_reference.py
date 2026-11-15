"""Local reference transcription, never sends audio to a speech API."""
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('HF_HOME', str(ROOT / 'cache/huggingface'))
os.environ['HF_HUB_DISABLE_XET'] = '1'
from faster_whisper import WhisperModel
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

audio = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'reference/rem-source-stereo.wav'
started = time.monotonic()
model = WhisperModel(str(ROOT / 'cache/whisper-small'), device='cpu', compute_type='int8', cpu_threads=6)
waveform, sample_rate = sf.read(audio, dtype='float32', always_2d=True)
waveform = waveform.mean(axis=1)
if sample_rate != 16000:
    divisor = math.gcd(sample_rate, 16000)
    waveform = resample_poly(waveform, 16000 // divisor, sample_rate // divisor).astype(np.float32)
segments, info = model.transcribe(waveform, language='ja', beam_size=5,
                                 vad_filter=True, word_timestamps=False,
                                 condition_on_previous_text=False)
rows = []
for segment in segments:
    row = {'start': segment.start, 'end': segment.end, 'text': segment.text,
           'avg_logprob': segment.avg_logprob, 'no_speech_prob': segment.no_speech_prob}
    rows.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
out = {'source': str(audio), 'engine': 'faster-whisper-small',
       'language': info.language, 'duration': info.duration,
       'elapsed_seconds': time.monotonic() - started,
       'note': 'Automatic transcription; reference text must be reviewed before synthesis.',
       'segments': rows}
target = audio.with_suffix('.transcript.json')
target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print('TRANSCRIPTION_COMPLETE', target, flush=True)
