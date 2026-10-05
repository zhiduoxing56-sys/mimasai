"""Same-weight approximation error versus independent training trajectory error."""
import json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import ROOT,config,Fixed
from src.data import cora
from src.sparse_reference import sparse,step

def main():
 c=config();out=ROOT/'results/representative';frozen=json.loads((out/'frozen.json').read_text());d=cora(node_count=64,sampling=frozen['sampling'],seed=frozen['sampling_seed']);mask=[i in d['splits']['train'] for i in range(64)];fixed_weights=json.loads((ROOT/f'build/representative/fixed-seed{frozen["initialization_seed"]}.json').read_text());fx=Fixed(dict(c,fraction_bits=c['training_reference']['fraction_bits']));p=[[round(v*fx.scale) for v in row] for row in d['propagation']];x=[[round(v*fx.scale) for v in row] for row in d['features']];w=json.loads((ROOT/f'build/representative/h{frozen["hidden"]}-lr{frozen["learning_rate"]}-seed{frozen["initialization_seed"]}.json').read_text());rows=[]
 for it in (0,32,64,96,160,320):
  tr,_,_=step(sparse(p),sparse(x),fixed_weights[str(it)],d['labels'],mask,fx,frozen['learning_rate'],c['training_reference']['probability_fraction_bits']);ft,_,_=step(sparse(d['propagation']),sparse(d['features']),w[str(it)],d['labels'],mask,learning_rate=frozen['learning_rate']);scores=[[v/4096 for v in row] for row in tr['logits']];high=[]
  for row in scores:
   exp=[math.exp(v-max(row)) for v in row];high.append([v/sum(exp) for v in exp])
  prob=[[v/(1<<c['training_reference']['probability_fraction_bits']) for v in row] for row in tr['probabilities']];rows.append(dict(iteration=it,same_fixed_logits_probability_max_error=max(abs(a-b) for rr,hh in zip(prob,high) for a,b in zip(rr,hh)),classification_equal_same_fixed_logits=all(max(range(7),key=lambda j:rr[j])==max(range(7),key=lambda j:hh[j]) for rr,hh in zip(prob,high)),probability_sum_min=min(map(sum,prob)),probability_sum_max=max(map(sum,prob)),independently_trained_float_fixed_probability_max_difference=max(abs(a-b) for rr,hh in zip(prob,ft['probabilities']) for a,b in zip(rr,hh)),layers_max_difference={key:max(abs(a/4096-b) for rr,hh in zip(tr[key],ft[key]) for a,b in zip(rr,hh)) for key in ('transform0','activation_input','hidden','transform1','logits')}))
 (out/'numeric.json').write_text(json.dumps(dict(status='REFERENCE_ONLY',rows=rows,scope='Independent trajectories can differ because floor rounding biases approximate updates; not exact equivalence. Iteration320 violates primary weight policy and is diagnostic only.'),indent=2)+'\n');print(json.dumps(rows[-2]))
if __name__=='__main__':main()
