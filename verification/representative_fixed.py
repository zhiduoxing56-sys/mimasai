"""Frozen mixed-precision integer reference and independent operand guard audit."""
import copy,json,random,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import config,Fixed,ROOT
from src.data import cora
from src.sparse_reference import sparse,step
from src.numerical import training_reference
from src.metrics import evaluate
from src.ranges import radius,operand
from verification.representative import topology
OUT=ROOT/'results/representative';PRIVATE=ROOT/'build/representative'

def guard(p,x,w,tr,fx):
 f=fx.scale.bit_length()-1;limits={role:radius(operand(role,f)) for role in ('feature','weight','propagation','state','error','backprop_state','gradient')};names=lambda role:limits[role];h=tr['hidden'];d=tr['logit_gradient'];trans=lambda a:list(map(list,zip(*a)))
 cases=[('XW0',x,w[0],'feature','weight'),('PT0',p,tr['transform0'],'propagation','state'),('HW1',h,w[1],'state','weight'),('PT1',p,tr['transform1'],'propagation','state'),('dT1',trans(p),d,'propagation','error'),('dW1',trans(h),tr['backprop1'],'state','backprop_state'),('dH',tr['backprop1'],trans(w[1]),'backprop_state','weight'),('dT0',trans(p),[[v if z>0 else 0 for v,z in zip(rr,zz)] for rr,zz in zip(tr['backprop_hidden'],tr['activation_input'])],'propagation','backprop_state'),('dW0',trans(x),tr['backprop0'],'feature','backprop_state')]
 violations=[];maxnorm=0
 for name,a,b,ka,kb in cases:
  for values,k in ((a,ka),(b,kb)):
   if any(v< -names(k) or v>=names(k) for row in values for v in row):violations.append(dict(operation=name,reason='operand interval',operand=k,min=min(v for row in values for v in row),max=max(v for row in values for v in row)))
  degree=len(b)
  if degree*names(ka)*names(kb)>=1<<31:
   norms=[sum(abs(v) for v in row) for row in a];cap=((1<<31)-1)//names(kb);maxnorm=max(maxnorm,max(norms)/fx.scale)
   if max(norms)>cap:violations.append(dict(operation=name,reason='secret row L1 would reject',maximum_units=max(norms),cap_units=cap))
 for name,values,role in [('activation_input',tr['activation_input'],'state'),('backprop_hidden',tr['backprop_hidden'],'backprop_state'),('gradient0',tr['gradient0'],'gradient'),('gradient1',tr['gradient1'],'gradient'),('next_weights',tr['next_weights'][0]+tr['next_weights'][1],'weight')]:
  if any(v< -names(role) or v>=names(role) for row in values for v in row):violations.append(dict(operation=name,reason='output interval',operand=role,min=min(v for row in values for v in row),max=max(v for row in values for v in row)))
 return violations

def main():
 c=config();frozen=json.loads((OUT/'frozen.json').read_text());cc=copy.deepcopy(c);cc['fraction_bits']=c['training_reference']['fraction_bits'];cc['training_reference']['loss_mode']='range_reduced';fx=Fixed(cc);results=[];started=time.perf_counter()
 for seed in c['data_experiment']['representative']['seeds']:
  d=cora(node_count=64,sampling=frozen['sampling'],seed=frozen['sampling_seed']);n=64;ff=len(d['feature_columns']);h=frozen['hidden'];rng=random.Random(seed);w=[[[round(rng.gauss(0,.2)*fx.scale) for _ in range(h)] for _ in range(ff)],[[round(rng.gauss(0,.2)*fx.scale) for _ in range(7)] for _ in range(h)]];p=[[round(v*fx.scale) for v in row] for row in d['propagation']];x=[[round(v*fx.scale) for v in row] for row in d['features']];mask=[i in d['splits']['train'] for i in range(n)];curves=[];refs=[];first_violation=None;audits=[];checkpoint={}
  for it in range(frozen['iterations']+1):
   tr,neww,audit=step(sparse(p),sparse(x),w,d['labels'],mask,fx,frozen['learning_rate'],c['training_reference']['probability_fraction_bits']);violations=guard(p,x,w,tr,fx)
   if violations and first_violation is None:first_violation=dict(iteration=it,cases=violations)
   if seed==c['data_experiment']['representative']['seeds'][0] and it<2:
    encoded=[[[v%fx.mod for v in row] for row in layer] for layer in w];full,nw,_=training_reference([[v%fx.mod for v in row] for row in p],[[v%fx.mod for v in row] for row in x],encoded,d['labels'],mask,cc)
    for key in full:
     actual=[tr['loss']] if key=='loss' else [v for layer in tr[key] for row in layer for v in row] if key=='next_weights' else [v for row in tr[key] for v in row]
     assert full[key]==[v%fx.mod for v in actual],key
   if it in c['data_experiment']['representative']['evaluation_checkpoints']:
    metrics=evaluate(d,[[v/(1<<c['training_reference']['probability_fraction_bits']) for v in row] for row in tr['probabilities']]);curves.append(dict(iteration=it,loss=tr['loss']/fx.scale,metrics=metrics,minimum_probability_units=min(v for row in tr['probabilities'] for v in row),maximum_raw_partial=max(a['max_abs_partial_sum'] for a in audit),violations=violations));checkpoint[str(it)]=w
   if seed==c['data_experiment']['representative']['seeds'][0]:refs.append(tr)
   audits.extend(dict(iteration=it,**a) for a in audit);w=neww
  name=f'fixed-seed{seed}';(PRIVATE/(name+'.json')).write_text(json.dumps(checkpoint));results.append(dict(seed=seed,curves=curves,first_protocol_guard_violation=first_violation,range_audits=audits));print(json.dumps(dict(seed=seed,first_protocol_guard_violation=first_violation,final={k:(v['accuracy'],v['macro_f1']) for k,v in curves[-1]['metrics'].items()})),flush=True)
 (PRIVATE/'primary-fixed-traces.json').write_text(json.dumps(refs));report=dict(status='FROZEN_FIXED_REFERENCE_PASS',frozen=frozen,training_fraction=12,probability_fraction=14,results=results,dense_sparse_two_step_bitwise=True,seconds=time.perf_counter()-started);(OUT/'fixed.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
