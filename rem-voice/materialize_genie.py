"""Expand external weights offline to avoid large protobuf copies at server boot."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import argparse

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'models/dafeiyu-zh-sparkle-v1'
OUT = ROOT/'models/dafeiyu-zh-sparkle-runtime-v1'
parser=argparse.ArgumentParser()
parser.add_argument('--source',default=str(SOURCE))
parser.add_argument('--output',default=str(OUT))
parser.add_argument('--bert-dir',default=None)
parser.add_argument('--profile',default=None)
args=parser.parse_args();SOURCE=Path(args.source);OUT=Path(args.output)
OUT.mkdir(exist_ok=True,parents=True)
for name in ['t2s_shared', 'vits']:
    data = np.fromfile(SOURCE/f'{name}_fp16.bin', dtype=np.float16)
    data.astype(np.float32).tofile(OUT/f'{name}_fp32.bin')
    del data
for name in ['t2s_encoder_fp32.bin','t2s_encoder_fp32.onnx',
        't2s_first_stage_decoder_fp32.onnx','t2s_stage_decoder_fp32.onnx',
        'vits_fp32.onnx','reference-features.npz']:
    shutil.copy2(SOURCE/name, OUT/name)
if args.bert_dir:
    bert=Path(args.bert_dir);destination=OUT/'chinese-bert';destination.mkdir(exist_ok=True)
    for name in ['bert-q8.onnx','tokenizer.json','manifest.json']:
        shutil.copy2(bert/name,destination/name)
    (OUT/'profile.json').write_text(json.dumps({'language':'zh','profile':args.profile or 'dafeiyu-zh-sparkle-v1'}),encoding='utf-8')
def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
manifest = {p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)}
    for p in OUT.rglob('*') if p.is_file() and p != OUT/'manifest.json'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('MATERIALIZED',sum(x['bytes'] for x in manifest.values()))
