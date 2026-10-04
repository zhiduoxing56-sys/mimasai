"""Training checkpoint shares -> local publication -> bounded shared inference."""
import argparse,copy,json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import C,ROOT,session,launch
from src.model import binding
from src.reference import Fixed,graph,precise_softmax
from src.numerical import probability_reference
OUT=ROOT/'results/continuation';OUT.mkdir(parents=True,exist_ok=True)
def main():
 args=argparse.ArgumentParser();args.add_argument('--indexed',action='store_true');args=args.parse_args()
 train=json.loads((OUT/('training-indexed.json' if args.indexed else 'training.json')).read_text());ftrain=C['training_reference']['fraction_bits'];f=C['fraction_bits'];dims=[C['graph_reference']['nodes'],len(C['graph_reference']['features'][0]),C['model_reference']['hidden_width'],C['model_reference']['classes']];n,features,h,classes=dims;count=features*h+h*classes;node_order=C['graph_reference']['node_order'];b12=binding(secrets.token_hex(16),node_order,features,h,classes,ftrain);b7=binding(secrets.token_hex(16),node_order,features,h,classes,f)
 # Verifier expected values from independent reference, never fed as reconstructed
 # model to servers. Their inputs below are actual existing checkpoint shares.
 oldref=train['reference_traces'][-1]['next_weights'];signed=lambda v:v if v<(1<<31) else v-(1<<32);converted=[signed(v)//(1<<(ftrain-f))%(1<<32) for v in oldref];w=[[[converted[i*h+j] for j in range(h)] for i in range(features)],[[converted[features*h+i*classes+j] for j in range(classes)] for i in range(h)]]
 _,_,p=graph(C['graph_reference']);fx=Fixed(C);P=fx.encode(p);X=fx.encode(C['graph_reference']['features']);trace=fx.forward(P,X,w,'transform_then_aggregate');fields=['transform0','activation_input','hidden','transform1','logits'];expected_scores=[v for key in fields for row in trace[key] for v in row];score_offset=len(expected_scores)-n*classes;pf=C['probability_fraction_bits'];scaled_scores=[[fx.signed(v)*(1<<(pf-f)) for v in row] for row in trace['logits']];probs,_=probability_reference(scaled_scores,pf);flat=lambda a:[v for row in a for v in row]
 plain=[dict(type='publish',count=count,x=[0]*count,source_fraction=ftrain,model=b12,expected=oldref),dict(type='publish',count=count,x=[],use_previous=True,source_fraction=ftrain,model=b7,expected=converted),dict(type='gcn_scores',input_feature_order=b7['feature_order'],dims=dims,fraction=f,model=b7,x=flat(X),p=flat(P),expected=expected_scores),dict(type='precision_up',count=n*classes,source_fraction=f,fraction=pf,x=[],use_previous=True,previous_slice=[score_offset,n*classes],expected=flat(scaled_scores)),dict(type='probability',count=n*classes,dims=[n,classes],fraction=pf,x=[],use_previous=True,expected=flat(probs))]
 d,s,dealer=session(32,plain)
 source=ROOT/'build/stage2'/train['session']
 for role in (0,1):
  outputs=list((source/f'S{role}').glob('output-*.json'));assert len(outputs)==1
  own_checkpoint=json.loads(outputs[0].read_text())['shares'][-1][-count:]
  path=d/f'S{role}/input.json';job=json.loads(path.read_text());job['operations'][0]['x']=own_checkpoint;path.write_text(json.dumps(job))
 attempt,metrics=launch(d,s,32,timeout=180);assert all(m['success'] for m in metrics),metrics
 outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
 for idx,op in enumerate(plain):assert [(a+b)%(1<<32) for a,b in zip(outs[0][idx],outs[1][idx])]==[v%(1<<32) for v in op['expected']],idx
 assert all(m['preprocessing']['consumed']==dealer['generated'] for m in metrics)
 for role in (0,1):
  for b in (b12,b7):
   file=json.loads((d/f'S{role}/model-{b["model_id"]}.json').read_text());assert not any('hash' in key or 'digest' in key for key in file['binding']) and file['role']==role
  assert outs[role][0]!=json.loads(list((source/f'S{role}').glob('output-*.json'))[0].read_text())['shares'][-1][-count:]
 high=precise_softmax([[fx.signed(v)/fx.scale for v in row] for row in trace['logits']]);err=max(abs(a/(1<<pf)-float(b)) for row,rr in zip(probs,high) for a,b in zip(row,rr))
 report=dict(status='PASS_TRAIN_SHARED_PUBLISH_BOUNDED_TWO_LAYER_MPC_PROBABILITY',source_training_session=train['session'],session=s,models=[b12,b7],dealer=dealer,servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],probability_fraction_bits=pf,probability_error=err,probability_sums=[sum(row)/(1<<pf) for row in probs],classification_equal=all(row.index(max(row))==rr.index(max(rr)) for row,rr in zip(probs,high)),reference=trace,range_audit=fx.audit,scope='Constrained pre-normalized graph; all-MPC inference, HE variant privacy remains blocked; no active auth')
 (OUT/('publication-indexed.json' if args.indexed else 'publication.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['status','wire_bytes','rounds','probability_error','probability_sums','classification_equal']},indent=2))
if __name__=='__main__':main()
