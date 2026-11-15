"""Convert the approved base weights; keep all intermediate files for audit."""
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'Genie-TTS/src/genie_tts'
OUT = ROOT / 'models/rem-ja-genie-v1'
CACHE = ROOT / 'cache/genie-conversion'
PRETRAINED = ROOT / 'GPT-SoVITS-v2Pro/GPT_SoVITS/pretrained_models'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

if __name__ == '__main__':
    # Conversion does not need the audio runtime, resource downloads, or server.
    package = types.ModuleType('genie_tts')
    package.__path__ = [str(SOURCE)]
    sys.modules['genie_tts'] = package
    from genie_tts.Converter.v2.T2SConverter import T2SModelConverter
    from genie_tts.Converter.v2.VITSConverter import VITSConverter
    from genie_tts.Converter.v2.EncoderConverter import EncoderConverter
    from genie_tts.Converter.v2ProPlus.PromptEncoderConverter import PromptEncoderConverter
    import torch
    torch.set_num_threads(2)
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    gpt = str(PRETRAINED / 's1v3.ckpt')
    sovits = str(PRETRAINED / 'v2Pro/s2Gv2ProPlus.pth')
    v2 = SOURCE / 'Data/v2'
    pp = SOURCE / 'Data/v2ProPlus'
    stages = [
        T2SModelConverter(gpt, str(v2/'Models/t2s_stage_decoder_fp32.onnx'),
            str(v2/'Models/t2s_first_stage_decoder_fp32.onnx'),
            str(v2/'Keys/t2s_onnx_keys.txt'), str(OUT), str(CACHE)),
        VITSConverter(sovits, str(pp/'Models/vits_fp32.onnx'),
            str(pp/'Keys/vits_weights.txt'), str(OUT), str(CACHE)),
        EncoderConverter(gpt, sovits, str(v2/'Models/t2s_encoder_fp32.onnx'), str(OUT)),
        PromptEncoderConverter(sovits, str(pp/'Models/prompt_encoder_fp32.onnx'),
            str(pp/'Keys/prompt_encoder_weights.txt'), str(OUT), str(CACHE)),
    ]
    for stage in stages:
        print('CONVERT', type(stage).__name__, flush=True)
        stage.run_full_process()
    manifest = {'source': json.loads((ROOT/'genie-source.json').read_text()),
        'inputs': {Path(p).name: digest(Path(p)) for p in (gpt,sovits)},
        'files': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)}
            for p in OUT.iterdir() if p.is_file() and p.name != 'manifest.json'}}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('CONVERTED', len(manifest['files']), 'files', flush=True)
