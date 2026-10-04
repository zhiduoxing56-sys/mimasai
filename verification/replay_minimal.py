"""Clean-source replay: never copies historical shares, keys or ledgers."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];(ROOT/'results/continuation').mkdir(parents=True,exist_ok=True);OUT=ROOT/'results/replay';OUT.mkdir(parents=True,exist_ok=True)
start=time.monotonic()
for file,args in [('stage1.py',[]),('training.py',['--indexed']),('publication.py',['--indexed']),('two_layer_he.py',[]),('he_private_decryption.py',['--columns','3','--two-layers'])]:
 with (OUT/(file+'.log')).open('w') as log:
  subprocess.run([sys.executable,str(ROOT/'verification'/file)]+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
read=lambda name:json.loads((ROOT/'results/continuation'/name).read_text())
train=read('training-indexed.json');pub=read('publication-indexed.json');he=read('two-layer-he.json')
assert pub['source_training_session']==train['session']
result=dict(status='PASS_CLEAN_SOURCE_FRESH_MATERIAL_REPLAY',scope='Existing shared train/publish/infer and real HE arithmetic; legacy HE view privacy still blocked',sessions=[train['session'],pub['session']]+[x['session'] for x in he['runs']],model_ids=[x['model_id'] for x in pub['models']],legacy_he_key_sizes=[x['setup'].get('public_key_bytes') for x in he['runs']],losses=train['losses'],probability_error=pub['probability_error'],he_status=he['status'],wall_seconds=time.monotonic()-start)
protected=json.loads((ROOT/'results/security-round/he-private-two-layer-boolean.json').read_text())
result.update(protected_he_status=protected['status'],protected_he_key_ids=protected['key_ids'],protected_he_wire_bytes=protected['wire_bytes'],protected_he_rounds=protected['rounds'])
result['sessions'].append(protected['session'])
result['scope']='Shared train/publish/infer and protected real HE two-layer scores; legacy conversion diagnostic only'
(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
