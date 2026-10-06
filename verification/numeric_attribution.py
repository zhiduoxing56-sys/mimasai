"""Same-checkpoint one-step ablations; never changes protocol semantics."""
import copy,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import ROOT,config,Fixed
from src.data import cora
from src.sparse_reference import sparse,trans,multiply,step
from src.numerical import probability_reference
from verification.representative_fixed import guard

def experiment(p,x,w,labels,mask,lr,approx=False,dot_floor=False,prob_down=False,average_floor=False,update_floor=False):
 s=4096;pf=14;count=sum(mask);h=len(w[0][0]);classes=7;n=len(x);features=len(w[0]);events=[]
 def floor(v,name,enabled):
  if not enabled:return v
  value=math.floor(v);events.append((name,value-v));return value
 def mm(a,b,cols,name):
  raw=multiply(sparse(a),sparse(b),cols)
  return [[floor(v/s,name,dot_floor) for v in row] for row in raw]
 t0=mm(x,w[0],h,'XW0');z0=mm(p,t0,h,'PT0');hidden=[[max(0,v) for v in row] for row in z0];t1=mm(hidden,w[1],7,'HW1');z1=mm(p,t1,7,'PT1')
 if approx:
  prob,_=probability_reference([[round(v*(1<<(pf-12))) for v in row] for row in z1],pf);pr=[[v/4 for v in row] for row in prob]
 else:
  pr=[]
  for row in z1:
   ex=[math.exp((v-max(row))/s) for v in row];pr.append([v/sum(ex)*s for v in ex])
 d=[[(floor(pr[i][j],'probability_f14_to_f12',prob_down)-(s if labels[i]==j else 0))/count for j in range(7)] if mask[i] else [0]*7 for i in range(n)]
 d=[[floor(v,'average_signed',average_floor) for v in row] for row in d]
 transpose=lambda a:list(map(list,zip(*a)))
 dt1=mm(transpose(p),d,7,'dT1');dw1=mm(transpose(hidden),dt1,7,'dW1');dh=mm(dt1,transpose(w[1]),h,'dH');dz=[[v if z>0 else 0 for v,z in zip(row,zz)] for row,zz in zip(dh,z0)];dt0=mm(transpose(p),dz,h,'dT0');dw0=mm(transpose(x),dt0,h,'dW0')
 nw=[[[v-floor(g*lr,'parameter_update',update_floor) for v,g in zip(row,rr)] for row,rr in zip(layer,grad)] for layer,grad in zip(w,(dw0,dw1))]
 groups={}
 for name,residual in events:
  group=groups.setdefault(name,dict(count=0,sum_units=0,min_units=0,max_units=0));group['count']+=1;group['sum_units']+=residual;group['min_units']=min(group['min_units'],residual);group['max_units']=max(group['max_units'],residual)
 return dict(logits=z1,probabilities=[[v/s for v in row] for row in pr],gradient0=dw0,gradient1=dw1,next_weights=nw,truncation_residuals=groups)

def values(v):
 if isinstance(v,list):
  for item in v:yield from values(item)
 else:yield v

def distance(a,b):
 diff=[x-y for x,y in zip(values(a),values(b))];return dict(max_abs=max(map(abs,diff)),mean=sum(diff)/len(diff),mean_abs=sum(map(abs,diff))/len(diff))

def main():
 c=config();out=ROOT/'results/representative';f=json.loads((out/'frozen.json').read_text());d=cora(node_count=64,sampling=f['sampling'],seed=f['sampling_seed']);wfixed=json.loads((ROOT/f'build/representative/fixed-seed{f["initialization_seed"]}.json').read_text());wfloat=json.loads((ROOT/f'build/representative/h{f["hidden"]}-lr{f["learning_rate"]}-seed{f["initialization_seed"]}.json').read_text());p=[[round(v*4096) for v in row] for row in d['propagation']];x=[[round(v*4096) for v in row] for row in d['features']];mask=[i in d['splits']['train'] for i in range(64)];rows=[];fx=Fixed(dict(c,fraction_bits=12))
 variants=[('quantized_inputs_exact_arithmetic',{}),('probability_approximation',dict(approx=True)),('each_dot_floor',dict(approx=True,dot_floor=True)),('probability_precision_down',dict(approx=True,dot_floor=True,prob_down=True)),('gradient_average_floor',dict(approx=True,dot_floor=True,prob_down=True,average_floor=True)),('parameter_update_floor',dict(approx=True,dot_floor=True,prob_down=True,average_floor=True,update_floor=True))]
 for it in (0,32,64,96,160,320):
  w=wfixed[str(it)];refs=[]
  for name,args in variants:refs.append((name,experiment(p,x,w,d['labels'],mask,f['learning_rate'],**args)))
  trace,_,audit=step(sparse(p),sparse(x),w,d['labels'],mask,fx,f['learning_rate'],14)
  for key in ('logits','gradient0','gradient1','next_weights'):
   assert list(values(refs[-1][1][key]))==list(values(trace[key])),(it,key)
  actualprob=[[v/16384 for v in row] for row in trace['probabilities']];assert actualprob==refs[-1][1]['probabilities']
  deltas=[]
  for (before,a),(after,b) in zip(refs,refs[1:]):
   deltas.append(dict(change=after,relative_to=before,probability=distance(b['probabilities'],a['probabilities']),gradients_units=distance([b['gradient0'],b['gradient1']],[a['gradient0'],a['gradient1']]),next_weights_units=distance(b['next_weights'],a['next_weights']),truncation_residuals=b['truncation_residuals']))
  ft,_,_=step(sparse(d['propagation']),sparse(d['features']),wfloat[str(it)],d['labels'],mask,learning_rate=f['learning_rate'])
  rows.append(dict(iteration=it,ablations=deltas,independent_trajectory_probability=distance(actualprob,ft['probabilities']),same_integer_logits_probability=distance(actualprob,experiment(p,x,w,d['labels'],mask,f['learning_rate'],dot_floor=True)['probabilities']),maximum_actual_product=max(a['max_abs_product'] for a in audit),maximum_actual_partial=max(a['max_abs_partial_sum'] for a in audit),signed_32_limit=1<<31,protocol_guard_cases=guard(p,x,w,trace,fx),full_ablation_matches_existing_integer_reference=True))
 fixed=json.loads((out/'fixed.json').read_text());violation=fixed['results'][0]['first_protocol_guard_violation']
 index=violation['iteration'];boundary_audit=[a for a in fixed['results'][0]['range_audits'] if a['iteration']==index];weight_case=next(q for q in violation['cases'] if q['operation']=='next_weights')
 boundary=dict(preupdate_iteration_index=index,proposed_completed_update=index+1,weight_min=weight_case['min'],weight_max=weight_case['max'],permitted_weight_units=[-16384,16384],maximum_actual_product=max(a['max_abs_product'] for a in boundary_audit),maximum_actual_partial=max(a['max_abs_partial_sum'] for a in boundary_audit),signed_32_limit=1<<31,source='Existing fixed-reference range audit and output guard record, no shared execution',guard_cases=violation['cases'])

 result=dict(status='SAME_CHECKPOINT_ONE_STEP_ATTRIBUTION',rows=rows,first_long_training_policy_violation=violation,weight_boundary=boundary,
  scope='Cumulative conditional ablations at identical existing integer weights, quantized X/P. Effects depend on ordering; not independent causal totals. Dot floor once after each matrix dot, never per multiplication. Approximate p-y gradient kept. No new training trajectory or materials. Integer protocol unchanged.',weight_rejection='src/operators.py train_step final e.check_range(nextw, operand(weight,12)); also XW0/HW1 and dH operand checks. Weight interval [-16384,16384) at f12 ([-4,4)). Current guard rejection is protocol applicability, not evidence of integer overflow; actual products/partials reported separately.')
 (out/'numeric-attribution.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],violation=violation),indent=2))
if __name__=='__main__':main()
