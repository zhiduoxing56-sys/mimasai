"""Predeclared public sampling and train/validation-only float selection."""
import copy,json,random,time,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import config,ROOT
from src.sparse_reference import sparse,step
from src.metrics import classification,evaluate
OUT=ROOT/'results/representative';OUT.mkdir(exist_ok=True);PRIVATE=ROOT/'build/representative';PRIVATE.mkdir(exist_ok=True)

def topology(d):
 n=len(d['labels']);adj=[set() for _ in range(n)]
 for u,v,_ in d['edges']:adj[u].add(v);adj[v].add(u)
 seen=set();components=[]
 for root in range(n):
  if root in seen:continue
  stack=[root];seen.add(root);size=0
  while stack:
   u=stack.pop();size+=1
   for v in adj[u]:
    if v not in seen:seen.add(v);stack.append(v)
  components.append(size)
 return dict(nodes=n,features=len(d['feature_columns']),citation_records=len(d['edges']),unique_pairs=sum(map(len,adj))//2,components=sorted(components,reverse=True),isolated_without_added_loops=sum(not row for row in adj),class_counts={name:dict(Counter(d['labels'][i] for i in ids)) for name,ids in d['splits'].items()},missing_training_classes=sorted(set(range(7))-set(d['labels'][i] for i in d['splits']['train'])),edge_homophily=sum(d['labels'][u]==d['labels'][v] for u,v,_ in d['edges'])/len(d['edges']) if d['edges'] else None)

def main():
 c=config();spec=c['data_experiment']['representative'];sampling=[];runs=[];started=time.perf_counter()
 for strategy in spec['strategies']:
  for seed in spec['seeds']:
   d=cora(node_count=64,sampling=strategy,seed=seed);sampling.append(dict(strategy=strategy,seed=seed,topology=topology(d),node_order=d['node_order'],splits=d['splits'],preprocessing=d['preprocessing'],label_policy=d['public_labels_used_for_sampling_and_split']))
 (OUT/'sampling.json').write_text(json.dumps(sampling,indent=2)+'\n')
 # Three predefined initializations on the identical primary sampled graph.
 # Other sampling seeds are held for post-freeze replication, not selected by test.
 d=cora(node_count=64,sampling='stratified_frontier',seed=spec['primary_seed']);p=sparse(d['propagation']);x=sparse(d['features']);mask=[i in d['splits']['train'] for i in range(64)];features=len(x) and len(d['feature_columns'])
 for h in spec['candidate_hidden_widths']:
  for lr in spec['candidate_learning_rates']:
   for seed in spec['seeds']:
    rng=random.Random(seed);w=[[[rng.gauss(0,.2) for _ in range(h)] for _ in range(features)],[[rng.gauss(0,.2) for _ in range(7)] for _ in range(h)]];curves=[];checkpoints={};t=time.perf_counter()
    for it in range(spec['reference_budget']+1):
     tr,neww,_=step(p,x,w,d['labels'],mask,learning_rate=lr)
     if it in spec['evaluation_checkpoints']:
      pred=[max(range(7),key=lambda j:row[j]) for row in tr['probabilities']];row=dict(iteration=it,loss=tr['loss'],train=classification(d['labels'],pred,d['splits']['train'],7),validation=classification(d['labels'],pred,d['splits']['validation'],7));curves.append(row);checkpoints[str(it)]=copy.deepcopy(w)
     w=neww
    name=f'h{h}-lr{lr}-seed{seed}';(PRIVATE/(name+'.json')).write_text(json.dumps(checkpoints));run=dict(name=name,hidden=h,learning_rate=lr,initialization_seed=seed,curves=curves,seconds=time.perf_counter()-t);runs.append(run);print(json.dumps(dict(name=name,seconds=run['seconds'],validation=[(q['iteration'],q['validation']['accuracy'],q['validation']['macro_f1']) for q in curves])),flush=True)
    (OUT/'selection-progress.json').write_text(json.dumps(dict(status='TEST_WITHHELD',runs=runs),indent=2)+'\n')
 scores=[]
 for h in spec['candidate_hidden_widths']:
  for lr in spec['candidate_learning_rates']:
   subset=[r for r in runs if r['hidden']==h and r['learning_rate']==lr]
   for it in spec['evaluation_checkpoints'][1:]:scores.append(dict(hidden=h,learning_rate=lr,iterations=it,validation_macro_f1=sum(next(q for q in r['curves'] if q['iteration']==it)['validation']['macro_f1'] for r in subset)/len(subset)))
 chosen=max(scores,key=lambda q:(q['validation_macro_f1'],-q['hidden'],-q['iterations'],-q['learning_rate']));freeze=dict(status='FROZEN_BEFORE_TEST_EVALUATION',sampling='stratified_frontier',sampling_seed=spec['primary_seed'],initialization_seed=spec['seeds'][0],**chosen,selection='Mean validation macro F1 across three predefined initializations; all test metrics withheld',frozen_at_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat());(OUT/'frozen.json').write_text(json.dumps(freeze,indent=2)+'\n')
 # Only now access test metrics for every initialization of the chosen config.
 effects=[]
 for seed in spec['seeds']:
  name=f'h{chosen["hidden"]}-lr{chosen["learning_rate"]}-seed{seed}';w=json.loads((PRIVATE/(name+'.json')).read_text())[str(chosen['iterations'])];tr,_,_=step(p,x,w,d['labels'],mask,learning_rate=chosen['learning_rate']);effects.append(dict(seed=seed,metrics=evaluate(d,tr['probabilities'])))
 report=dict(status='FROZEN_FLOAT_EXPERIMENT',chosen=freeze,sampling=sampling,runs=runs,effects=effects,seconds=time.perf_counter()-started,test_policy='No test metric used for sample/config/seed selection; initial seeds predeclared; other sample seeds remain independent topology evidence')
 (OUT/'float.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(freeze),flush=True)
if __name__=='__main__':main()
