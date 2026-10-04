"""Verifier-only initialization coverage; does not alter current secret loss."""
import copy,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import config,Fixed,graph
from src.numerical import probability_reference
from verification.stage2 import session,launch
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/security-round';OUT.mkdir(parents=True,exist_ok=True)
c=config();c['fraction_bits']=c['training_reference']['fraction_bits'];f=c['fraction_bits'];fx=Fixed(c);s=fx.scale;p=fx.encode(graph(c['graph_reference'])[2]);x=fx.encode(c['graph_reference']['features']);base=c['model_reference'];samples=[];bad_example=None
for scale in [0,.25,.5,1,2,3]:
 for kind,second in [('original',base['initial_weights'][1]),('zero',[[0,0]]*3)]+[(f'contrast-{v}',[[v,-v]]*3) for v in [.25,.5,1,2,-.25,-.5,-1,-2]]:
  w=[fx.encode([[v*scale for v in row] for row in base['initial_weights'][0]]),fx.encode(second)]
  try:trace=fx.forward(p,x,w,'transform_then_aggregate')
  except OverflowError:samples.append(dict(scale=scale,second=kind,state='wide_integer_overflow'));continue
  bounded=all(-8*s<=fx.signed(v)<8*s for key in ['transform0','activation_input','hidden','transform1'] for row in trace[key] for v in row)
  prob,_=probability_reference([[fx.signed(v) for v in row] for row in trace['logits']],f)
  targets=[prob[i][base['labels'][i]] for i,on in enumerate(base['training_mask']) if on];fails=[i for i,on in enumerate(base['training_mask']) if on and prob[i][base['labels'][i]]<s//4]
  samples.append(dict(scale=scale,second=kind,state='accepted' if bounded and not fails else 'loss_domain_reject' if bounded else 'forward_bound_reject',verifier_target_units=targets,verifier_failure_nodes=fails))
  if bounded and fails and bad_example is None:bad_example=prob
assert bad_example is not None
labels=[[s if j==label else 0 for j in range(2)] for label in base['labels']];plain=dict(type='loss',count=10,dims=[5,2],fraction=f,training_mask=base['training_mask'],x=[v for row in bad_example for v in row],y=[v for row in labels for v in row],expected=[])
d,sid,_=session(32,[plain]);_,metrics=launch(d,sid,32);assert not any(m['success'] for m in metrics) and any(m['error']=='LOSS_PROBABILITY_DOMAIN' for m in metrics);_,restart=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
# Proposed range-reduced log reference only, no secret implementation claim.
def log_ref(q):
 if not 1<=q<=s:raise ValueError('positive fixed probability required')
 k=0;u=q
 while u<s//2:u*=2;k+=1
 v=s-u;power=v;out=0
 for j in range(1,9):
  out+=power*(s//j)//s
  if j<8:power=power*v//s
 return out+k*round(s*math.log(2))
errs=[abs(log_ref(q)/s+math.log(q/s)) for q in range(1,s+1)]
r=dict(status='PASS_LOSS_LIMIT_COVERAGE_CURRENT_PROTOCOL_REJECTS',cases=samples,counts={name:sum(v['state']==name for v in samples) for name in ['accepted','loss_domain_reject','forward_bound_reject','wide_integer_overflow']},secret_failure=dict(session=sid,errors=[m['error'] for m in metrics],restarts=[m['error'] for m in restart],only_batch_flags_open=True),candidate_log=dict(status='PLAINTEXT_REFERENCE_AND_DESIGN_ONLY',domain_units=[1,s],range_reduction='u=q*2^k in [S/2,S]; -ln(q/S)=k ln2 -ln(u/S)',k_max=f,log_degree=8,grid=len(errs),max_absolute_error=max(errs),zero_probability='reject batch in proposed path; no public target probability',needed_secret_primitives=['MSB/secret normalization shift','positive batch check','existing exact product truncation','secret k times public ln2'],gradient_policy='Current approximate standard gradient retained; no trainer algorithm change'),scope='Synthetic verifier-known initialization grid, not all initialization distributions; no secret target probabilities logged by servers')
(OUT/'loss-domain.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],counts=r['counts'],candidate_log_error=max(errs)),indent=2))
