"""Owner-only word-feature control: identical data, split and selection rule."""
import copy,json,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import ROOT,config
from src.data import cora
from src.sparse_reference import sparse,step
from src.metrics import classification,evaluate

def main():
 c=config();spec=c['data_experiment']['representative'];out=ROOT/'results/representative';frozen=json.loads((out/'frozen.json').read_text());d=cora(node_count=64,sampling=frozen['sampling'],seed=frozen['sampling_seed']);mask=[i in d['splits']['train'] for i in range(64)];x=sparse(d['features']);identity=[[(i,1.0)] for i in range(64)];runs=[];weights={};started=time.perf_counter()
 # Predeclared original GCN grid/checkpoints/seeds, same macro-F1 rule.
 # Test indices are never passed to classification during selection.
 for h in spec['candidate_hidden_widths']:
  for lr in spec['candidate_learning_rates']:
   for seed in spec['seeds']:
    rng=random.Random(seed);w=[[[rng.gauss(0,.2) for _ in range(h)] for _ in d['feature_columns']],[[rng.gauss(0,.2) for _ in range(7)] for _ in range(h)]];curves=[];saved={}
    for it in range(spec['reference_budget']+1):
     tr,nw,_=step(identity,x,w,d['labels'],mask,learning_rate=lr)
     if it in spec['evaluation_checkpoints']:
      pred=[max(range(7),key=lambda j:row[j]) for row in tr['probabilities']];curves.append(dict(iteration=it,train=classification(d['labels'],pred,d['splits']['train'],7),validation=classification(d['labels'],pred,d['splits']['validation'],7)));saved[it]=copy.deepcopy(w)
     w=nw
    name=f'{h}:{lr}:{seed}';weights[name]=saved;runs.append(dict(name=name,hidden=h,learning_rate=lr,seed=seed,curves=curves))
 scores=[]
 for h in spec['candidate_hidden_widths']:
  for lr in spec['candidate_learning_rates']:
   subset=[r for r in runs if r['hidden']==h and r['learning_rate']==lr]
   for it in spec['evaluation_checkpoints'][1:]:scores.append(dict(hidden=h,learning_rate=lr,iterations=it,validation_macro_f1=sum(next(q for q in r['curves'] if q['iteration']==it)['validation']['macro_f1'] for r in subset)/len(subset)))
 selected=max(scores,key=lambda q:(q['validation_macro_f1'],-q['hidden'],-q['iterations'],-q['learning_rate']))
 freeze=dict(**selected,selection=spec['selection'],sampling=frozen['sampling'],sampling_seed=frozen['sampling_seed'],seeds=spec['seeds'],test_used=False)
 (out/'feature-control-frozen.json').write_text(json.dumps(freeze,indent=2)+'\n')
 effects=[];matched=[]
 for seed in spec['seeds']:
  for label,h,lr,it,dest in [('validation_selected',selected['hidden'],selected['learning_rate'],selected['iterations'],effects),('matched_gcn_budget_160',frozen['hidden'],frozen['learning_rate'],160,matched)]:
   w=weights[f'{h}:{lr}:{seed}'][it];tr,_,_=step(identity,x,w,d['labels'],mask,learning_rate=lr);dest.append(dict(seed=seed,metrics=evaluate(d,tr['probabilities'])))
 # Label-independent reference results already exist; no new graph selection.
 replication=json.loads((out/'replication.json').read_text());label_free=[r for r in replication['runs'] if r['strategy'] in ('uniform','multi_start')]
 report=dict(status='OWNER_ONLY_FEATURE_CONTROL',model='Two-layer ReLU classifier, zero biases, identity propagation: only word features',selection=freeze,runs=runs,effects=effects,matched_160=matched,
  node_order=d['node_order'],splits=d['splits'],archive_sha256=d['archive_sha256'],label_names=d['label_names'],label_free_existing_reference=label_free,
  seconds=time.perf_counter()-started,scope='No cryptographic material generated. Same primary graph nodes/features/splits and validation-only rule; stratified sampling uses labels and alters natural topology/distribution. Existing tests were already known; this is a post-hoc specified control, not a fresh blinded benchmark. No sample or seed replacement.')
 (out/'feature-control.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(selection=freeze,seconds=report['seconds'],test=[(r['seed'],r['metrics']['test']['accuracy'],r['metrics']['test']['macro_f1']) for r in effects]),indent=2))
if __name__=='__main__':main()
