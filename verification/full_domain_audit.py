"""Owner-side diagnosis: fixed domain, declared operand limits, conservative L1."""
import json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import config,Fixed,ROOT
from src.sparse_reference import sparse,step,trans,multiply
from src.numerical import probability_reference
c=config();cc=dict(c,fraction_bits=c['training_reference']['fraction_bits']);fx=Fixed(cc);d=cora(full_graph=True);n=len(d['node_order']);f=len(d['feature_columns']);h=c['model_reference']['hidden_width'];classes=7;rng=random.Random(c['data_experiment']['initialization_seed']);w=[[[round(rng.gauss(0,.2)*fx.scale) for j in range(h)] for i in range(f)],[[round(rng.gauss(0,.2)*fx.scale) for j in range(classes)] for i in range(h)]];p=[[(j,round(v*fx.scale)) for j,v in row] for row in d['propagation']];x=[[(j,round(v*fx.scale)) for j,v in row] for row in sparse(d['features'])];mask=[i in d['splits']['train'] for i in range(n)];first=None;maximum=0
for it in range(c['data_experiment']['maximum_reference_iterations']):
 try:
  tr,w,audit=step(p,x,w,d['labels'],mask,fx,c['model_reference']['learning_rate']);maximum=max(maximum,max(a['max_abs_partial_sum'] for a in audit))
  for name,role in [('transform0','state'),('activation_input','state'),('transform1','state'),('logits','score'),('backprop_hidden','state'),('backprop0','state')]:
   bound=fx.scale*2**c['range_policy']['operand_bound_exponents'][role];values=[v for row in tr[name] for v in row]
   if first is None and any(v< -bound or v>=bound for v in values):first=dict(iteration=it,group=name,min_units=min(values),max_units=max(values),bound_units=bound)
 except (ValueError,OverflowError) as e:
  failure=dict(iteration=it,reason=str(e));break
else:failure=None
columns=trans(x,f);cap=((1<<31)-1)//(fx.scale*2**c['range_policy']['operand_bound_exponents']['state']);largest=max(sum(abs(v) for j,v in row) for row in columns);result=dict(status='FULL_CORA_LIMITS_DIAGNOSED_NOT_SECURE_EXECUTION',dimensions=[n,f,h,classes],first_operand_range_violation=first,fixed_loss_failure=failure,max_checked_partial_sum=maximum,X_transpose_max_row_l1=largest,X_transpose_state_cap=cap,first_transform_arithmetic_mask_payload_bytes=n*f*h*8,frame_limit=c['mpc']['max_frame_bytes'],scope='Independent owner-side probe; no online failure location/value disclosure, no claimed full secure training')
out=ROOT/'results/real-data/full-domain-audit.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
