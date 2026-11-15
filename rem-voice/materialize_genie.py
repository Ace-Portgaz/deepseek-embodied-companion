"""Expand external weights offline to avoid large protobuf copies at server boot."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'models/rem-ja-genie-v1'
OUT = ROOT/'models/rem-ja-genie-runtime-v1'
OUT.mkdir(exist_ok=True,parents=True)
for name in ['t2s_shared', 'vits']:
    data = np.fromfile(SOURCE/f'{name}_fp16.bin', dtype=np.float16)
    data.astype(np.float32).tofile(OUT/f'{name}_fp32.bin')
    del data
for name in ['t2s_encoder_fp32.bin','t2s_encoder_fp32.onnx',
        't2s_first_stage_decoder_fp32.onnx','t2s_stage_decoder_fp32.onnx',
        'vits_fp32.onnx','reference-features.npz']:
    shutil.copy2(SOURCE/name, OUT/name)
def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
manifest = {p.name:{'bytes':p.stat().st_size,'sha256':digest(p)}
    for p in OUT.iterdir() if p.is_file() and p.name != 'manifest.json'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('MATERIALIZED',sum(x['bytes'] for x in manifest.values()))
