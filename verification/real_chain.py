"""Real Cora shared checkpoint -> publication -> protected HE and MPC comparison."""
import argparse,copy,json,os,secrets,struct,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import config,Fixed,precise_softmax
from src.numerical import probability_reference
from src.model import binding
from src.mpc import private_write
from src.he import native,binary_write,file_hash
from verification.stage2 import ROOT,session,launch
from verification.trained_he_chain import run
OUT=ROOT/'results/real-data';MOD=1<<32
flat=lambda a:[v for row in a for v in row]

def publish(train,data):
 c=config();fx=Fixed(c);n=len(data['node_order']);ff,h,classes=train['dimensions'][1:];ft=c['training_reference']['fraction_bits'];f=c['fraction_bits'];pf=c['probability_fraction_bits'];count=ff*h+h*classes;layout=dict(feature_order=[f'word-{j}' for j in data['feature_columns']],class_order=data['label_names']);b12=binding(secrets.token_hex(16),data['node_order'],ff,h,classes,ft,**layout);b7=binding(secrets.token_hex(16),data['node_order'],ff,h,classes,f,**layout);checkpoint=train['checkpoint'];source=Path(checkpoint['directory']);own=[json.loads((source/f'S{r}/output-{checkpoint["attempt"]}.json').read_text())['shares'][0][-count:] for r in (0,1)];ref=[(a+b)%MOD for a,b in zip(*own)];converted=[(v if v<MOD//2 else v-MOD)//(1<<(ft-f))%MOD for v in ref];w=[[[converted[i*h+j] for j in range(h)] for i in range(ff)],[[converted[ff*h+i*classes+j] for j in range(classes)] for i in range(h)]];P=fx.encode(data['propagation']);X=fx.encode(data['features']);trace=fx.forward(P,X,w,'transform_then_aggregate');scores=[v for key in ['transform0','activation_input','hidden','transform1','logits'] for v in flat(trace[key])];scaled=[[fx.signed(v)*(1<<(pf-f)) for v in row] for row in trace['logits']];prob,_=probability_reference(scaled,pf)
 plain=[dict(type='publish',count=count,x=[0]*count,source_fraction=ft,model=b12,expected=ref),dict(type='publish',count=count,x=[],use_previous=True,source_fraction=ft,model=b7,expected=converted),dict(type='gcn_scores',input_feature_order=b7['feature_order'],dims=[n,ff,h,classes],fraction=f,model=b7,x=flat(X),p=flat(P),expected=scores),dict(type='precision_up',count=n*classes,source_fraction=f,fraction=pf,x=[],use_previous=True,previous_slice=[len(scores)-n*classes,n*classes],expected=flat(scaled)),dict(type='probability',count=n*classes,dims=[n,classes],fraction=pf,x=[],use_previous=True,expected=flat(prob))]
 d,s,dealer=session(32,plain)
 for r in (0,1):
  path=d/f'S{r}/input.json';job=json.loads(path.read_text());job['operations'][0]['x']=own[r];path.write_text(json.dumps(job)+'\n')
 started=time.perf_counter();attempt,metrics=launch(d,s,32,timeout=300);assert all(m['success'] for m in metrics),metrics
 outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
 for i,op in enumerate(plain):assert [(a+b)%MOD for a,b in zip(outs[0][i],outs[1][i])]==[v%MOD for v in op['expected']],i
 assert all(m['preprocessing']['consumed']==dealer['generated'] for m in metrics)
 high=precise_softmax(fx.decode(trace['logits']));error=max(abs(a/(1<<pf)-float(b)) for row,rr in zip(prob,high) for a,b in zip(row,rr));report=dict(status='PASS_REAL_SHARED_CHECKPOINT_PUBLICATION',source_training_session=checkpoint['session'] if 'session' in checkpoint else source.name,source_training_iteration=checkpoint['iteration'],session=s,models=[b12,b7],activation_bits=f+c['range_policy']['operand_bound_exponents']['state']+1,dealer=dealer,servers=metrics,wall_seconds=time.perf_counter()-started,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],probability_error=error,classification_equal=all(row.index(max(row))==rr.index(max(rr)) for row,rr in zip(prob,high)),reference=trace,range_audit=fx.audit,probability_sums=[sum(row)/(1<<pf) for row in prob]);(OUT/'publication.json').write_text(json.dumps(report,indent=2)+'\n');return report

def owner_bundle(data):
 c=config();fx=Fixed(c);p=fx.encode(data['propagation']);assert all(0<=v<=fx.scale for row in p for v in row);n=len(p);h=c['model_reference']['hidden_width'];sid=secrets.token_hex(16);d=ROOT/'build/stage3'/sid
 for name in ('S0','S1','V'):(d/name).mkdir(parents=True,mode=0o700)
 binary_write(d/'V/propagation.bin',struct.pack('<'+'I'*(n*n),*flat(p)));started=time.perf_counter();setup=native(['setup',d,c['he_execution_degree'],c['ring_bits'],*c['he_coefficient_bits'],n,h]);setup['wall_seconds']=time.perf_counter()-started
 public=dict(package_id=secrets.token_hex(16),key_ids=[file_hash(d/f'S{r}/eval.pk')[:32] for r in (0,1)],parameters_id=file_hash(d/'S0/parameters.seal'),degree=c['he_execution_degree'],ring_bits=c['ring_bits'],shape=[n,h],node_order=data['node_order'],column_order=[f'hidden-{j}' for j in range(h)],input_scale=1<<c['fraction_bits'],output_scale=1<<(2*c['fraction_bits']))
 assert public['key_ids'][0]!=public['key_ids'][1]
 for r in (0,1):
  own=d/f'S{r}';files=['eval.pk','eval.gk','peer.sk','parameters.seal']+[f'rows/{i}.ct' for i in range(n)];private_write(own/'he.json',dict(role=r,public=public,local_integrity={name:file_hash(own/name) for name in files}));assert not (own/'self.sk').exists();assert (own/'peer.sk').read_bytes()==(d/f'V/key{1-r}.sk').read_bytes()
 return d,sid,public,setup,p,None,dict(features=fx.encode(data['features']))

def main():
 p=argparse.ArgumentParser();p.add_argument('--faults',action='store_true');p.add_argument('--reuse-publication',action='store_true');args=p.parse_args();data=cora();train=json.loads((OUT/'reference.json').read_text());assert train['status']=='SHARED_TRAINING_PASS';report=json.loads((OUT/'publication.json').read_text()) if args.reuse_publication else publish(train,data);runs=[]
 for activation in ('boolean','fss'):
  for route in ('shared','he'):
   print(json.dumps(dict(progress='running',route=route,activation=activation)),flush=True);result=run(report,route,activation,bundle_factory=lambda:owner_bundle(data),output_directory=OUT);runs.append(result);print(json.dumps(dict(progress='passed',route=route,activation=activation,seconds=result['wall_seconds'],bytes=result['wire_bytes'],rounds=result['rounds'])),flush=True)
 assert all(r['restored_verifier_traces']==runs[0]['restored_verifier_traces'] for r in runs)
 faults=[run(report,'he','boolean',fault,bundle_factory=lambda:owner_bundle(data),output_directory=OUT) for fault in ('checkpoint','scale','parameter','feature_order','column_order','exhaustion','disconnect')] if args.faults else []
 result=dict(status='PASS_CORA_16_TRAIN_PUBLISH_PROTECTED_HE_SECRET_PROBABILITY',dimensions=train['dimensions'],training_steps=train['secure_steps'],training_checkpoint=train['checkpoint'],publication_session=report['session'],same_model_bitwise_all_six_trace_groups=True,runs=[{k:v for k,v in r.items() if k not in ('servers','restored_verifier_traces')} for r in runs],faults=faults,limits=train['limits']+['Trusted noncolluding offline, passive local processes; no active authentication','Legacy ciphertext conversion remains security blocked']);(OUT/'chain.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],dimensions=result['dimensions'],training_steps=result['training_steps'])),flush=True)
if __name__=='__main__':main()
