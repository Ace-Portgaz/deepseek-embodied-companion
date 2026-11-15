"""Reproducible small Mandarin-only GPT-SoVITS fine-tune. Never deploys."""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parent
REPO=ROOT/'GPT-SoVITS-v2Pro'
DATA=ROOT/'datasets/dafeiyu-zh-sparkle-v1'
EXP=ROOT/'training/dafeiyu-zh-sparkle-v1'
PRE=REPO/'GPT_SoVITS/pretrained_models'
PY=Path(sys.executable)
NAME='dafeiyu-zh-sparkle-v1'

def run(label,args,env):
    print('START',label,flush=True);start=time.time()
    with (EXP/(label+'.log')).open('a',encoding='utf-8') as log:
        proc=subprocess.run([str(PY),'-u','-X','utf8',*map(str,args)],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT)
    if proc.returncode:raise RuntimeError(f'{label} failed; see {EXP/(label+".log")}')
    print('DONE',label,round(time.time()-start,1),'seconds',flush=True)

def main():
    global DATA,EXP,NAME
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','train','all'])
    parser.add_argument('--name',default=NAME)
    parser.add_argument('--dataset',default=str(DATA))
    a=parser.parse_args()
    if not __import__('re').fullmatch(r'[a-zA-Z0-9-]{1,80}',a.name):raise ValueError('Invalid experiment name')
    DATA=Path(a.dataset).resolve();NAME=a.name;EXP=ROOT/'training'/NAME
    EXP.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    ids={Path(r['file']).name for r in manifest['train']}
    assert not ids.intersection(Path(r['file']).name for r in manifest['heldout'])
    for r in manifest['train']:
        assert hashlib.sha256(Path(r['file']).read_bytes()).hexdigest()==r['sha256']
    env=os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
      HF_HOME=str(ROOT/'cache/huggingface'),TORCH_HOME=str(ROOT/'cache/torch'),
      NUMBA_CACHE_DIR=str(ROOT/'cache/numba'),NLTK_DATA=str(ROOT/'cache/nltk_data'),
      OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',
      PYTHONPATH=os.pathsep.join([str(REPO),str(REPO/'GPT_SoVITS')]),
      PATH=str(ROOT/'bin')+os.pathsep+env.get('PATH',''),
      inp_text=str(DATA/'train.list'),inp_wav_dir=str(DATA/'wavs'),exp_name=NAME,
      i_part='0',all_parts='1',opt_dir=str(EXP),is_half='True',version='v2ProPlus',
      _CUDA_VISIBLE_DEVICES='0',hz='25hz',language='en_US',
      bert_pretrained_dir=str(PRE/'chinese-roberta-wwm-ext-large'),
      cnhubert_base_dir=str(PRE/'chinese-hubert-base'),
      pretrained_s2G=str(PRE/'v2Pro/s2Gv2ProPlus.pth'),
      s2config_path=str(REPO/'GPT_SoVITS/configs/s2v2ProPlus.json'),
      sv_path=str(PRE/'sv/pretrained_eres2netv2w24s4ep4.ckpt'))
    if a.stage in ['prepare','all']:
        for script in ['1-get-text.py','2-get-hubert-wav32k.py','2-get-sv.py','3-get-semantic.py']:
            run(script,[REPO/'GPT_SoVITS/prepare_datasets'/script],env)
        texts=(EXP/'2-name2text-0.txt').read_text(encoding='utf-8').splitlines()
        assert {x.split('\t')[0] for x in texts}==ids,'Missing text/BERT features'
        (EXP/'2-name2text.txt').write_text('\n'.join(texts)+'\n',encoding='utf-8')
        sem=(EXP/'6-name2semantic-0.tsv').read_text(encoding='utf-8').splitlines()
        if sem[0].split('\t')[0]=='item_name':sem=sem[1:]
        assert {x.split('\t')[0] for x in sem}==ids,'Missing semantic features'
        (EXP/'6-name2semantic.tsv').write_text('item_name\tsemantic_audio\n'+'\n'.join(sem)+'\n',encoding='utf-8')
        for name in ids:
            for sub,suffix in [('3-bert','.pt'),('4-cnhubert','.pt'),('7-sv_cn','.pt'),('5-wav32k','')]:
                assert (EXP/sub/(name+suffix)).is_file(),(sub,name)
        (EXP/'prepared.json').write_text(json.dumps({'samples':len(ids),'language':'zh','heldout':len(manifest['heldout'])}),encoding='utf-8')
        print('ALL_FEATURES_VERIFIED',len(ids),flush=True)
    if a.stage in ['train','all']:
        assert (EXP/'prepared.json').is_file(),'Prepare and verify features first'
        for d in ['weights-sovits','weights-gpt','logs_s2_v2ProPlus']:(EXP/d).mkdir(exist_ok=True)
        s2=json.loads((REPO/'GPT_SoVITS/configs/s2v2ProPlus.json').read_text())
        s2['train'].update(batch_size=2,epochs=8,text_low_lr_rate=.4,pretrained_s2G=str(PRE/'v2Pro/s2Gv2ProPlus.pth'),
            pretrained_s2D=str(PRE/'v2Pro/s2Dv2ProPlus.pth'),if_save_latest=True,if_save_every_weights=True,
            save_every_epoch=4,gpu_numbers='0',grad_ckpt=True,lora_rank=32)
        s2['model']['version']='v2ProPlus';s2['data']['exp_dir']=str(EXP);s2['s2_ckpt_dir']=str(EXP)
        s2.update(save_weight_dir=str(EXP/'weights-sovits'),name=NAME,version='v2ProPlus')
        (EXP/'s2.json').write_text(json.dumps(s2,indent=2),encoding='utf-8')
        run('train-sovits',[REPO/'GPT_SoVITS/s2_train.py','--config',EXP/'s2.json'],env)
        s1=yaml.safe_load((REPO/'GPT_SoVITS/configs/s1longer-v2.yaml').read_text())
        s1['train'].update(batch_size=4,epochs=10,save_every_n_epoch=5,if_save_every_weights=True,
            if_save_latest=True,if_dpo=False,half_weights_save_dir=str(EXP/'weights-gpt'),exp_name=NAME)
        s1['data']['num_workers']=2
        s1.update(pretrained_s1=str(PRE/'s1v3.ckpt'),train_semantic_path=str(EXP/'6-name2semantic.tsv'),
            train_phoneme_path=str(EXP/'2-name2text.txt'),output_dir=str(EXP/'logs_s1_v2ProPlus'))
        (EXP/'s1.yaml').write_text(yaml.safe_dump(s1),encoding='utf-8')
        run('train-gpt',[REPO/'GPT_SoVITS/s1_train.py','--config_file',EXP/'s1.yaml'],env)
        print('TRAINING_COMPLETE; audition required before any deployment',flush=True)

if __name__=='__main__':main()
