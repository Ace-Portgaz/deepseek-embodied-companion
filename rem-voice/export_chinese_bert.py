"""Export GPT-SoVITS' exact third-last Chinese BERT layer for CPU inference."""
from pathlib import Path
import gc, hashlib, json, os
ROOT=Path(__file__).resolve().parent
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
import numpy as np
import torch
from transformers import AutoModelForMaskedLM,AutoTokenizer
from onnxruntime.quantization import quantize_dynamic,QuantType
import onnxruntime as ort

torch.set_num_threads(2)
SOURCE=ROOT/'GPT-SoVITS-v2Pro/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
OUT=ROOT/'models/chinese-bert-cpu-v1';OUT.mkdir(parents=True,exist_ok=True)
tokenizer=AutoTokenizer.from_pretrained(SOURCE)
loaded=AutoModelForMaskedLM.from_pretrained(SOURCE).eval()
bert=loaded.bert;total=len(bert.encoder.layer)
bert.encoder.layer=bert.encoder.layer[:total-2]
del loaded;gc.collect()

class Features(torch.nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,input_ids,attention_mask,token_type_ids):
        return self.model(input_ids=input_ids,attention_mask=attention_mask,token_type_ids=token_type_ids,return_dict=False)[0]

model=Features(bert).eval()
texts=['你好，大肥鱼。','今天想吃白米饭。','我看见你挥手啦，先歇一会儿吧。','银行的行长喜欢听音乐。','一个人也可以过得很开心。']
references=[]
for text in texts:
    inputs=tokenizer(text,return_tensors='pt')
    with torch.no_grad():ref=model(**inputs).numpy()
    references.append((text,{k:v.numpy() for k,v in inputs.items()},ref))
inputs=tokenizer(texts[0],return_tensors='pt')
fp=OUT/'bert-fp32.onnx';q8=OUT/'bert-q8.onnx'
if not fp.exists():
    with torch.no_grad():
        torch.onnx.export(model,tuple(inputs[k] for k in ('input_ids','attention_mask','token_type_ids')),str(fp),
          input_names=['input_ids','attention_mask','token_type_ids'],output_names=['hidden'],opset_version=17,
          dynamic_axes={n:{0:'batch',1:'sequence'} for n in ('input_ids','attention_mask','token_type_ids','hidden')},
          do_constant_folding=True,dynamo=False)
del model,bert;gc.collect()
print('EXPORTED',fp.stat().st_size,flush=True)
if not q8.exists():quantize_dynamic(str(fp),str(q8),weight_type=QuantType.QInt8,op_types_to_quantize=['MatMul'])
tokenizer.backend_tokenizer.save(str(OUT/'tokenizer.json'))
options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
sess=ort.InferenceSession(str(q8),sess_options=options,providers=['CPUExecutionProvider'])
checks=[]
for text,feed,ref in references:
    got=sess.run(None,feed)[0];a=got.reshape(-1);b=ref.reshape(-1)
    cos=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
    assert got.shape==ref.shape and np.isfinite(got).all() and cos>.97,(text,cos)
    checks.append({'text':text,'shape':list(got.shape),'cosine_to_float32':cos})
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
report={'source':'hfl/chinese-roberta-wwm-ext-large via locally verified GPT-SoVITS pretrained assets',
  'license':'Apache-2.0','original_layers':total,'exported_layers':total-2,
  'hidden_state':'original hidden_states[-3]','checks':checks,
  'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in [q8,OUT/'tokenizer.json']}}
(OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('QUANTIZED_VERIFIED',json.dumps(checks,ensure_ascii=False),flush=True)
