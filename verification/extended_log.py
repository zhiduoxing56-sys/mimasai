"""Independent verifier: every positive f12 unit, zero rejection, old 60 cases."""
import argparse,copy,json,math,sys,time
from decimal import Decimal,localcontext
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import C,ROOT,session,launch
from src.numerical import negative_log_reference,probability_reference
from src.reference import Fixed,graph
OUT=ROOT/'results/extended-log';OUT.mkdir(parents=True,exist_ok=True)
def execute(ops):
 d,s,dealer=session(32,ops);start=time.perf_counter();attempt,metrics=launch(d,s,32,timeout=240);wall=time.perf_counter()-start
 assert all(m['success'] for m in metrics),metrics
 outputs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
 for i,op in enumerate(ops):assert [(a+b)%(1<<32) for a,b in zip(outputs[0][i],outputs[1][i])]==op['expected']
 assert all(m['preprocessing']['consumed']==dealer['generated'] for m in metrics)
 return dict(session=s,dealer=dealer,servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],wall_seconds=wall)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--reuse-positive-results',action='store_true');args=parser.parse_args()
 f=C['training_reference']['fraction_bits'];scale=1<<f;runs=[]
 if args.reuse_positive_results:
  # Verifier-only re-audit of completed runs; never launch/reuse their materials.
  covered=set()
  for d in (ROOT/'build/stage2').iterdir():
   files=list((d/'S0').glob('output-*.json'))
   if len(files)!=1:continue
   job=json.loads((d/'S0/input.json').read_text());ops=job['operations']
   if len(ops)!=1 or ops[0]['type']!='negative_log' or ops[0]['fraction']!=f:continue
   attempt=files[0].stem[len('output-'):];metrics=[json.loads((d/f'S{r}/metrics-{attempt}.json').read_text()) for r in (0,1)]
   assert all(m['success'] for m in metrics)
   other=json.loads((d/'S1/input.json').read_text())['operations'][0];values=[(a+b)%(1<<32) for a,b in zip(ops[0]['x'],other['x'])];out=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'][0] for r in (0,1)]
   assert [(a+b)%(1<<32) for a,b in zip(*out)]==[negative_log_reference(q,f) for q in values];covered.update(values)
   runs.append(dict(session=job['session'],servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],completed_run_verifier_reaudit_only=True))
  assert covered==set(range(1,scale+1))
 else:
  for start in range(1,scale+1,256):
   values=list(range(start,min(start+256,scale+1)));runs.append(execute([dict(type='negative_log',count=len(values),fraction=f,x=values,expected=[negative_log_reference(q,f) for q in values])]))
 (OUT/'positive-domain.json').write_text(json.dumps(dict(status='PASS_ALL_POSITIVE_UNITS',count=scale,runs=runs),indent=2)+'\n')
 failures=[]
 for values in [[0],[1,0,scale],[scale+1],[(1<<32)-1]]:
  d,s,_=session(32,[dict(type='negative_log',count=len(values),fraction=f,x=values)]);attempt,metrics=launch(d,s,32)
  assert not any(m['success'] for m in metrics) and all(not (d/f'S{r}/output-{attempt}.json').exists() for r in (0,1));_,retry=launch(d,s,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in retry)
  failures.append(dict(session=s,values_known_only_to_verifier=values,errors=[m['error'] for m in metrics],restart=[m['error'] for m in retry]))
 cc=copy.deepcopy(C);cc['fraction_bits']=f;fx=Fixed(cc);p=fx.encode(graph(cc['graph_reference'])[2]);x=fx.encode(cc['graph_reference']['features']);base=cc['model_reference'];cases=[];ops=[]
 for a in [0,.25,.5,1,2,3]:
  for name,w1 in [('original',base['initial_weights'][1]),('zero',[[0,0]]*3)]+[(f'contrast-{v}',[[v,-v]]*3) for v in [.25,.5,1,2,-.25,-.5,-1,-2]]:
   w=[fx.encode([[v*a for v in row] for row in base['initial_weights'][0]]),fx.encode(w1)];trace=fx.forward(p,x,w,'transform_then_aggregate');prob,_=probability_reference([[fx.signed(v) for v in row] for row in trace['logits']],f);targets=[prob[i][base['labels'][i]] for i,on in enumerate(base['training_mask']) if on];assert min(targets)>0
   labels=[[scale if j==label else 0 for j in range(2)] for label in base['labels']];expected=sum(negative_log_reference(q,f) for q in targets)//sum(base['training_mask']);ops.append(dict(type='loss',count=10,dims=[5,2],fraction=f,training_mask=base['training_mask'],loss_mode='range_reduced',x=[v for row in prob for v in row],y=[v for row in labels for v in row],expected=[expected]));cases.append(dict(scale=a,second=name,old_limit_failed=min(targets)<scale//4,extended_loss_units=expected))
 coverage=[]
 for start in range(0,len(ops),10):
  coverage.append(execute(ops[start:start+10]))
  (OUT/'coverage-progress.json').write_text(json.dumps(coverage,indent=2)+'\n')
 
 with localcontext() as context:
  context.prec=60;assert int((Decimal(2).ln()*scale).to_integral_value())==round(scale*math.log(2))
  errors=[float(abs(Decimal(negative_log_reference(q,f))/scale+(Decimal(q)/scale).ln())) for q in range(1,scale+1)]
 result=dict(status='PASS_SECRET_EXTENDED_LOG_ALL_POSITIVE_F12_AND_60_INITIALIZATIONS',positive_units_checked=scale,max_absolute_log_error=max(errors),primitive_runs=runs,failures=failures,initializations=cases,old_failures_resolved=sum(v['old_limit_failed'] for v in cases),coverage=coverage,leakage='Only whole-batch positive/domain flags; no q, k, leading position or intermediate values opened',limits=['Zero quantized probabilities reject','Current gradient remains approximate standard p-y','60 cases validate loss only; full updates separately checked on effective initialization'])
 (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','positive_units_checked','max_absolute_log_error','old_failures_resolved']},indent=2))
if __name__=='__main__':main()
