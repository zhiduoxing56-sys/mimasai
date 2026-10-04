"""Clean-source complete trained model -> protected HE -> secret probability."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/replay';OUT.mkdir(parents=True,exist_ok=True)
start=time.monotonic()
for file,args in [('stage1.py',[]),('trained_he_chain.py',['--faults'])]:
 with (OUT/(file+'.log')).open('w') as log:subprocess.run([sys.executable,str(ROOT/'verification'/file)]+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
chain=json.loads((ROOT/'results/trained-he/summary.json').read_text());train=json.loads((ROOT/'results/continuation/training-indexed.json').read_text());publication=json.loads((ROOT/'results/continuation/publication-indexed.json').read_text())
assert chain['source_training_session']==train['session'] and chain['publication_session']==publication['session']
result=dict(status='PASS_CLEAN_SOURCE_FRESH_MATERIAL_REPLAY',scope='Actual shared training -> persisted published shares -> protected real HE two-layer scores -> secret approximate probabilities; both activations and same-model MPC comparison',sessions=[train['session'],publication['session']]+[r['session'] for r in chain['runs']]+[r['session'] for r in chain['faults']],model_ids=[chain['model_id']],protected_he_key_ids=[r['key_ids'] for r in chain['runs'] if r['route']=='he'],losses=train['losses'],probability_error=publication['probability_error'],chain_status=chain['status'],wall_seconds=time.monotonic()-start)
assert len(set(result['sessions']))==len(result['sessions'])
(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
