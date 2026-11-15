"""Offline reference-only encoders, with explicit Mandarin phonemes and BERT."""
from pathlib import Path
import argparse,gc,hashlib,json,os,sys,types
import numpy as np,onnxruntime as ort,soundfile as sf,soxr
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--model-dir',required=True);parser.add_argument('--reference',required=True)
args=parser.parse_args();out=Path(args.model_dir);ref=json.loads(Path(args.reference).read_text(encoding='utf-8'))
assert ref['language']=='all_zh'
os.environ['GENIE_DATA_DIR']=str(ROOT/'GenieData')
package=types.ModuleType('genie_tts');package.__path__=[str(ROOT/'Genie-TTS/src/genie_tts')];sys.modules['genie_tts']=package
from genie_tts.ModelManager import load_session_with_fp16_conversion
sys.path.insert(0,str(ROOT/'service'))
from chinese_bert import ChineseBert
from vendor_genie.Chinese.ChineseG2P import chinese_to_phones
options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
options.add_session_config_entry('session.intra_op.allow_spinning','0')
norm,_,phones,word2ph=chinese_to_phones(ref['text'])
bert=ChineseBert(ROOT/'models/chinese-bert-cpu-v1',options)
features=bert.features(norm,word2ph);del bert;gc.collect()
audio,sr=sf.read(ref['audio_path'],dtype='float32');assert audio.ndim==1
audio32=soxr.resample(audio,sr,32000,quality='HQ') if sr!=32000 else audio
audio16=soxr.resample(audio32,32000,16000,quality='HQ')[None,:]
hubert=load_session_with_fp16_conversion(str(ROOT/'GenieData/chinese-hubert-base/chinese-hubert-base.onnx'),
    str(ROOT/'GenieData/chinese-hubert-base/chinese-hubert-base_weights_fp16.bin'),['CPUExecutionProvider'],options)
ssl=hubert.run(None,{'input_values':audio16})[0];del hubert;gc.collect()
speaker=ort.InferenceSession(str(ROOT/'GenieData/speaker_encoder.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
embedding=speaker.run(None,{'waveform':audio16})[0];del speaker;gc.collect()
encoder=load_session_with_fp16_conversion(str(out/'prompt_encoder_fp32.onnx'),str(out/'prompt_encoder_fp16.bin'),['CPUExecutionProvider'],options)
ge,advanced=encoder.run(None,{'ref_audio':audio32[None,:],'sv_emb':embedding});del encoder
values=dict(ref_seq=np.array([phones],dtype=np.int64),ref_bert=features,ssl_content=ssl,ge=ge,ge_advanced=advanced)
for key,value in values.items():assert np.isfinite(value).all(),key
np.savez(out/'reference-features.npz',**values)
report={'language':'zh','reference_sha256':hashlib.sha256(Path(ref['audio_path']).read_bytes()).hexdigest(),
    'normalized_text':norm,'shapes':{k:list(v.shape) for k,v in values.items()},'bert_zero_fallback':False}
(out/'reference-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
