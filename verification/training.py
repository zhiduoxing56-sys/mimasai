"""Genuine shared fixed training on pre-normalized graph; separate verifier."""
import argparse,copy,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import Fixed,graph,loss_grad
from src.numerical import training_reference
from verification.stage2 import C,ROOT,session,launch,verify
OUT=ROOT/'results/continuation'
def main():
 args=argparse.ArgumentParser();args.add_argument('--indexed',action='store_true');args=args.parse_args()
 cc=copy.deepcopy(C);f=C['training_reference']['fraction_bits'];cc['fraction_bits']=f;fixed=Fixed(cc);_,_,p=graph(C['graph_reference']);m=C['model_reference'];P=fixed.encode(p);X=fixed.encode(C['graph_reference']['features']);W=[fixed.encode(l) for l in m['initial_weights']];n=len(P);features=len(X[0]);h=m['hidden_width'];classes=m['classes'];mask=m['training_mask'];flat=lambda a:[v for row in a for v in row]
 degree=n # public worst-case capacity, independent of the true neighbor counts
 indices=[];edge_weights=[]
 for row in P:
  entries=[(j,v) for j,v in enumerate(row) if v];entries += [(0,0)]*(degree-len(entries));indices.extend(j for j,v in entries);edge_weights.extend(v for j,v in entries)
 labels=[[fixed.scale if j==label else 0 for j in range(classes)] for label in m['labels']];plain=[];refs=[];audits=[]
 for it in range(C['training_reference']['iterations']):
  initialW=copy.deepcopy(W);trace,W,audit=training_reference(P,X,W,m['labels'],mask,cc);expected=[v for row in trace.values() for v in row];refs.append(trace);audits.extend(audit)
  plain.append(dict(type='train_step',dims=[n,features,h,classes],fraction=f,training_mask=mask,weights_previous=it>0,x=flat(X),p=flat(P),labels=flat(labels),y=flat(initialW[0])+flat(initialW[1]) if it==0 else [],expected=expected))
 if args.indexed:
  for op in plain:op.update(aggregation='indexed',degree=degree,indices=indices,edge_weights=edge_weights,p=[])
 d,s,dealer=session(32,plain);attempt,metrics=launch(d,s,32,timeout=180);assert all(x['success'] for x in metrics),metrics
 outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
 for it,op in enumerate(plain):assert [(a+b)%(1<<32) for a,b in zip(outs[0][it],outs[1][it])]==op['expected'],it
 assert all(x['preprocessing']['consumed']==dealer['generated'] for x in metrics)
 floatloss,floatgrad,_=loss_grad(p,C['graph_reference']['features'],m['initial_weights'],m['labels'],mask)
 gradfloat=flat(floatgrad[0])+flat(floatgrad[1]);gradfixed=refs[0]['gradient0']+refs[0]['gradient1'];graderror=max(abs(fixed.signed(a)/fixed.scale-b) for a,b in zip(gradfixed,gradfloat))
 study=[]
 for ff in (C['fraction_bits'],f):
  ccc=copy.deepcopy(C);ccc['fraction_bits']=ff;fx=Fixed(ccc);pp=fx.encode(p);xx=fx.encode(C['graph_reference']['features']);ww=[fx.encode(l) for l in m['initial_weights']];losses=[]
  for it in range(C['training_reference']['iterations']):tr,ww,_=training_reference(pp,xx,ww,m['labels'],mask,ccc);losses.append(tr['loss'][0]/fx.scale)
  study.append(dict(fraction_bits=ff,losses=losses))
 # Threshold units, equality, window reset, max iteration are checked as shares.
 ops=[]
 for prev,current,run,threshold,window,it,maxit in [(10,9,2,1,3,2,9),(10,8,2,1,3,2,9),(10,10,1,1,3,3,9),(10,7,0,1,3,9,9)]:
  valid=int(abs(prev-current)<=threshold);next_run=valid*(run+1);stop=int(next_run>=window or it>=maxit);ops.append(dict(type='convergence',count=1,x=[prev],y=[current],p=[run],threshold=threshold,window=window,iteration=it,maximum=maxit,open_stop=True,expected=[next_run,stop]))
 convergence,_=verify(32,ops,'secret_convergence')
 result=dict(status='PASS_THREE_INDEXED_SHARED_TRAIN_STEPS' if args.indexed else 'PASS_THREE_SHARED_TRAIN_STEPS_PRENORMALIZED_GRAPH',session=s,dealer=dealer,servers=metrics,reference_traces=refs,verifier_wide_audit=audits,precision_study=study,initial_float_loss=floatloss,first_gradient_float_max_error=graderror,losses=[t['loss'][0]/fixed.scale for t in refs],convergence=convergence,wire_bytes=sum(x['communication']['bytes_sent'] for x in metrics),rounds=metrics[0]['communication']['exchange_rounds'],limits=['Pre-normalized P input; private degree/sqrt normalization not implemented','Approximate standard p-y gradient, not derivative of approximate exp/log','No HE aggregation in training; shared matrix protocol used','Masks/labels input contract; trusted noncolluding offline; passive only'])
 assert result['losses'][-1]<result['losses'][0]
 (OUT/('training-indexed.json' if args.indexed else 'training.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],losses=result['losses'],precision_study=study,gradient_error=graderror,bytes=result['wire_bytes'],rounds=result['rounds']),indent=2))
if __name__=='__main__':main()
