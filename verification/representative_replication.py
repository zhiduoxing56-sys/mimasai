"""Post-freeze replications; no selection or replacement of the primary graph."""
import json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import config,Fixed,ROOT
from src.data import cora
from src.sparse_reference import sparse,step
from src.metrics import evaluate
from verification.representative import topology

def main():
 c=config();frozen=json.loads((ROOT/'results/representative/frozen.json').read_text());runs=[]
 for strategy in ('uniform','multi_start','stratified_frontier'):
  for seed in c['data_experiment']['representative']['seeds']:
   d=cora(node_count=64,sampling=strategy,seed=seed);ff=len(d['feature_columns']);h=frozen['hidden'];rng=random.Random(frozen['initialization_seed']);initial=[[[rng.gauss(0,.2) for _ in range(h)] for _ in range(ff)],[[rng.gauss(0,.2) for _ in range(7)] for _ in range(h)]];mask=[i in d['splits']['train'] for i in range(64)];curves=[]
   for mode in ('float','fixed'):
    fx=None
    if mode=='fixed':cc=dict(c,fraction_bits=c['training_reference']['fraction_bits']);fx=Fixed(cc)
    w=initial if fx is None else [[[round(v*fx.scale) for v in row] for row in layer] for layer in initial];p=d['propagation'] if fx is None else [[round(v*fx.scale) for v in row] for row in d['propagation']];x=d['features'] if fx is None else [[round(v*fx.scale) for v in row] for row in d['features']]
    try:
     for it in range(frozen['iterations']+1):
      tr,nw,_=step(sparse(p),sparse(x),w,d['labels'],mask,fx,frozen['learning_rate'],c['training_reference']['probability_fraction_bits'] if fx else None)
      if it in (0,96,160,frozen['iterations']):curves.append(dict(mode=mode,iteration=it,loss=tr['loss']/(fx.scale if fx else 1),metrics=evaluate(d,[[v/(1<<c['training_reference']['probability_fraction_bits']) for v in row] for row in tr['probabilities']] if fx else tr['probabilities'])))
      w=nw
    except (AssertionError,ValueError,OverflowError) as error:curves.append(dict(mode=mode,failure=str(error),iteration=it))
   runs.append(dict(strategy=strategy,sampling_seed=seed,initialization_seed=frozen['initialization_seed'],topology=topology(d),curves=curves));print(strategy,seed,flush=True)
 out=ROOT/'results/representative/replication.json';out.write_text(json.dumps(dict(status='POST_FREEZE_REPLICATION',frozen=frozen,selection_performed=False,runs=runs),indent=2)+'\n')
if __name__=='__main__':main()
