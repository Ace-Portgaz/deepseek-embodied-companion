"""Offline Chinese prosody features; no zero-feature fallback for Mandarin."""
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

class ChineseBert:
    def __init__(self,directory,options):
        directory=Path(directory)
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.session=ort.InferenceSession(str(directory/'bert-q8.onnx'),sess_options=options,
            providers=['CPUExecutionProvider'])

    def features(self,text,word2ph):
        if len(text)!=len(word2ph) or any(type(n) is not int or n<1 for n in word2ph):
            raise ValueError('Chinese phoneme alignment mismatch')
        encoded=self.tokenizer.encode(text)
        # Only normalized Chinese plus punctuation is accepted by this frontend.
        # Reject a tokenization mismatch rather than silently using wrong tones.
        positions=[i for i,(start,end) in enumerate(encoded.offsets) if end>start]
        if [encoded.offsets[i] for i in positions]!=[(i,i+1) for i in range(len(text))]:
            raise ValueError('Chinese tokenizer alignment mismatch')
        ids=np.array([encoded.ids],dtype=np.int64)
        hidden=self.session.run(None,{'input_ids':ids,'attention_mask':np.ones_like(ids),
            'token_type_ids':np.zeros_like(ids)})[0][0]
        result=np.repeat(hidden[positions],word2ph,axis=0).astype(np.float32)
        if result.shape!=(sum(word2ph),1024) or not np.isfinite(result).all():
            raise ValueError('Invalid Chinese BERT features')
        return result
