"""One actual shared update for each of the three old loss-domain failures."""
import copy,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import C,ROOT,session,launch
from src.reference import Fixed,graph
from src.numerical import training_reference,probability_reference
OUT=ROOT/'results/extended-log';OUT.mkdir(parents=True,exist_ok=True)
c=copy.deepcopy(C);c['fraction_bits']=c['training_reference']['fraction_bits'];c['training_reference']['loss_mode']='range_reduced';f=c['fraction_bits'];fx=Fixed(c);m=c['model_reference'];p=fx.encode(graph(c['graph_reference'])[2]);x=fx.encode(c['graph_reference']['features']);s=fx.scale;flat=lambda rows:[v for row in rows for v in row];cases=[];ops=[]
indices=[];weights=[]
for row in p:
 entries=[(j,v) for j,v in enumerate(row) if v]+[(0,0)]*(5-sum(v!=0 for v in row));indices.extend(j for j,v in entries);weights.extend(v for j,v in entries)
for scale in [0,.25,.5,1,2,3]:
 for name,second in [('original',m['initial_weights'][1]),('zero',[[0,0]]*3)]+[(f'contrast-{v}',[[v,-v]]*3) for v in [.25,.5,1,2,-.25,-.5,-1,-2]]:
  w=[fx.encode([[v*scale for v in row] for row in m['initial_weights'][0]]),fx.encode(second)];forward=fx.forward(p,x,w,'transform_then_aggregate');prob,_=probability_reference([[fx.signed(v) for v in row] for row in forward['logits']],f);targets=[prob[i][m['labels'][i]] for i,on in enumerate(m['training_mask']) if on]
  if min(targets)>=s//4:continue
  trace,_,audit=training_reference(p,x,w,m['labels'],m['training_mask'],c);labels=[[s if j==label else 0 for j in range(2)] for label in m['labels']];ops.append(dict(type='train_step',dims=[5,2,3,2],fraction=f,training_mask=m['training_mask'],loss_mode='range_reduced',aggregation='indexed',degree=5,indices=indices,edge_weights=weights,x=flat(x),p=[],labels=flat(labels),y=flat(w[0])+flat(w[1]),expected=[v for group in trace.values() for v in group]));cases.append(dict(scale=scale,second=name,loss_units=trace['loss'][0],wide_audit=audit))
assert len(ops)==3
d,sid,dealer=session(32,ops);start=time.perf_counter();attempt,metrics=launch(d,sid,32,timeout=240);wall=time.perf_counter()-start;assert all(m['success'] for m in metrics),metrics
out=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
for i,op in enumerate(ops):assert [(a+b)%(1<<32) for a,b in zip(out[0][i],out[1][i])]==[v%(1<<32) for v in op['expected']]
assert all(m['preprocessing']['consumed']==dealer['generated'] for m in metrics)
report=dict(status='PASS_ONE_SHARED_TRAIN_UPDATE_FOR_ALL_THREE_OLD_DOMAIN_FAILURES',session=sid,cases=cases,servers=metrics,dealer=dealer,wall_seconds=wall,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],scope='Three separate initializations, one step each; not 60 full trainings or long convergence')
(OUT/'failed-initialization-training.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['status','wall_seconds','wire_bytes','rounds']},indent=2))
