"""Actual training -> persisted shared publication -> same-model MPC/HE probability."""
import argparse,copy,json,math,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage3 import C,ROOT,bundle,check_he
from verification.stage2 import launch
from verification.he_private_decryption import oracle_round,audit_ring
from src.he import native
from src.mpc import VERSION,private_write
from src.numerical import probability_reference
OUT=ROOT/'results/trained-he';OUT.mkdir(parents=True,exist_ok=True);MOD=1<<32
flat=lambda rows:[v for row in rows for v in row]
signed=lambda v:v if v<1<<31 else v-MOD

def run(pub_report,route,activation,fault=None,*,bundle_factory=None,output_directory=OUT):
 output_directory.mkdir(parents=True,exist_ok=True)
 d,sid,pub,setup,p,_,inputs=(bundle_factory() if bundle_factory else bundle(5));n=len(p);f=C['fraction_bits'];pf=C['probability_fraction_bits'];model=pub_report['models'][-1];ff,h,c=model['dimensions'];source=ROOT/'build/stage2'/pub_report['session'];trace=pub_report['reference'];bounds=C['range_policy']['operand_bound_exponents'];k=lambda name:f+bounds[name]+1
 qs=native(['metadata',d/'S0'])['data_moduli'];pub['data_moduli']=qs
 os.link(d/'S0/parameters.seal',d/'parameters.seal');pub2=copy.deepcopy(pub);pub2.update(shape=[n,c],column_order=model['class_order'])
 for role in (0,1):
  own=d/f'S{role}';a=own/'he-layer0';a.mkdir(mode=0o700)
  for name in ['parameters.seal','eval.pk','eval.gk','peer.sk','rows','he.json']:(own/name).rename(a/name)
  doc=json.loads((a/'he.json').read_text());doc['public']=pub;(a/'he.json').write_text(json.dumps(doc))
  b=own/'he-layer1';b.mkdir(mode=0o700);(b/'rows').mkdir(mode=0o700)
  for name in ['parameters.seal','eval.pk','eval.gk','peer.sk']+[f'rows/{i}.ct' for i in range(n)]:os.link(a/name,b/name)
  doc['public']=pub2;private_write(b/'he.json',doc)
 plan=[dict(type='matmul',input_feature_order=model['feature_order'],dims=[n,ff,h],fraction=f,model=model,model_layer=0,bounds=[k('feature'),k('weight')],trace_raw=True)]
 def aggregate(public,width,slot,activation,offset):
  common=dict(count=n*width,fraction=f,k=pub_report.get('activation_bits',C['mpc']['activation_range_bits']),activation=activation,use_previous=True,previous_slice=[offset,n*width])
  return dict(common,model=model,model_layer=0 if slot=='he-layer0' else 1,type='he_aggregate',conversion='private_decryption',he=public,he_slot=slot,input_bound=k('state')) if route=='he' else dict(common,type='shared_aggregate',dims=[n,n,width],bounds=[k('propagation'),k('state')],trace_raw=True)
 plan+=[aggregate(pub,h,'he-layer0',activation,n*h),dict(type='matmul',dims=[n,h,c],fraction=f,model=model,model_layer=1,bounds=[k('state'),k('weight')],trace_raw=True,use_previous=True,previous_slice=[2*n*h,n*h]),aggregate(pub2,c,'he-layer1','none',n*c),dict(type='precision_up',count=n*c,source_fraction=f,fraction=pf,use_previous=True,previous_slice=[n*c,n*c]),dict(type='probability',count=n*c,dims=[n,c],fraction=pf,use_previous=True)]
 private_write(d/'public-plan.json',dict(session=sid,bits=32,plan=plan));start=time.perf_counter();dealer=subprocess.run([sys.executable,'-m','src.offline',str(d),str(d/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True);offline=json.loads(dealer.stdout);offline_seconds=time.perf_counter()-start
 jobs=[copy.deepcopy(plan) for _ in (0,1)]
 for role in (0,1):
  own=d/f'S{role}'
  # Only role-to-same-role persisted publication is transferred. No parameter
  # reconstruction or re-sharing; independently checked by this verifier.
  original=source/f'S{role}/model-{model["model_id"]}.json';target=own/original.name;shutil.copyfile(original,target);os.chmod(target,0o600);assert target.read_bytes()==original.read_bytes()
  old=json.loads((source/f'S{role}/input.json').read_text())['operations'][2]
  for op in jobs[role]:op['x']=[]
  jobs[role][0]['x']=old['x'] # same authorized input share, not fixture read online
  if route=='shared':
   for index in (1,3):jobs[role][index]['p']=old['p']
  private_write(d/f'S{role}/input.json',dict(version=VERSION,session=sid,role=role,bits=32,operations=jobs[role]))
 if fault=='feature_order':
  for role in (0,1):
   path=d/f'S{role}/input.json';doc=json.loads(path.read_text());doc['operations'][0]['input_feature_order']=list(reversed(doc['operations'][0]['input_feature_order']));path.write_text(json.dumps(doc))
 elif fault=='column_order':
  for role in (0,1):
   path=d/f'S{role}/input.json';doc=json.loads(path.read_text());doc['operations'][3]['he']['column_order']=list(reversed(doc['operations'][3]['he']['column_order']));path.write_text(json.dumps(doc))
 elif fault=='checkpoint':
  path=d/f'S0/model-{model["model_id"]}.json';doc=json.loads(path.read_text());doc['binding']['model_id']=secrets.token_hex(16);path.write_text(json.dumps(doc))
 elif fault in ('scale','parameter'):
  path=d/'S0/he-layer0/he.json';doc=json.loads(path.read_text());key='input_scale' if fault=='scale' else 'parameters_id';doc['public'][key]=doc['public'][key]*2 if fault=='scale' else secrets.token_hex(32);path.write_text(json.dumps(doc))
 elif fault=='exhaustion':
  for role in (0,1):
   path=d/f'S{role}/preprocessing.json';doc=json.loads(path.read_text());doc['materials']['arithmetic']=[];path.write_text(json.dumps(doc))
 start=time.perf_counter();attempt,metrics=launch(d,sid,32,worker='verification.he_private_fault_worker' if fault=='disconnect' else 'src.mpc_worker',timeout=240);wall=time.perf_counter()-start
 if fault:
  assert not any(m['success'] for m in metrics),metrics
  assert all(not (d/f'S{role}/output-{attempt}.json').exists() for role in (0,1))
  _,restart=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
  new_batch='relabel-'+secrets.token_hex(12)
  for role in (0,1):
   path=d/f'S{role}/preprocessing.json';doc=json.loads(path.read_text());doc['batch']=new_batch;path.write_text(json.dumps(doc))
  _,relabeled=launch(d,sid,32);assert all(m['error']=='RING_MATERIAL_REUSE' for m in relabeled)
  result=dict(fault=fault,status='PASS_NO_OUTPUT_FAILURE_AND_BURN',session=sid,errors=[m['error'] for m in metrics],restart=[m['error'] for m in restart],servers=metrics,relabel_errors=[m['error'] for m in relabeled]);(output_directory/f'fault-{fault}.json').write_text(json.dumps(result,indent=2)+'\n');return result
 assert all(m['success'] for m in metrics),metrics
 outs=[json.loads((d/f'S{role}/output-{attempt}.json').read_text())['shares'] for role in (0,1)];restored=[[(a+b)%MOD for a,b in zip(*parts)] for parts in zip(*outs)]
 # Expected linear raw values from independently recovered *published* model.
 ownw=[json.loads((source/f'S{role}/model-{model["model_id"]}.json').read_text())['shares'] for role in (0,1)];w=[(a+b)%MOD for a,b in zip(*ownw)];w0=[w[i*h:(i+1)*h] for i in range(ff)];w1=[w[ff*h+i*c:ff*h+(i+1)*c] for i in range(h)]
 def raw(a,b):
  rows=[]
  for row in a:
   for col in range(len(b[0])):
    parts=[signed(v)*signed(b[j][col]) for j,v in enumerate(row)];total=0
    for part in parts:
     assert -(1<<31)<=part<(1<<31);total+=part;assert -(1<<31)<=total<(1<<31)
    rows.append(total%MOD)
  return rows
 scaled=[[signed(v)*(1<<(pf-f)) for v in row] for row in trace['logits']];prob,_=probability_reference(scaled,pf)
 expected=[raw(inputs['features'],w0)+flat(trace['transform0']),raw(p,trace['transform0'])+flat(trace['activation_input'])+flat(trace['hidden']),raw(trace['hidden'],w1)+flat(trace['transform1']),raw(p,trace['transform1'])+flat(trace['logits']),flat(scaled),flat(prob)]
 expected=[[v%MOD for v in group] for group in expected]
 assert restored==expected,(route,activation)
 assert all(m['preprocessing']['consumed']==offline['generated'] for m in metrics)
 assert all(m['pid']!=os.getpid() and all(v.startswith(f'S{m["role"]}/') for v in m['loaded_private_files']) for m in metrics)
 audits=[];checks=0
 if route=='he':
  for public,key,slot in [(pub,'transform0','he-layer0'),(pub2,'transform1','he-layer1')]:
   audits.append(check_he(dict(directory=d,public=public,propagation=p,transform=trace[key],he_slot=slot)))
   for role in (0,1):checks+=oracle_round(d,d/f'S{role}'/slot,role,n,public['shape'][1],qs)
  assert audit_ring(d,qs)==9
  assert not any(t['type']=='he_masked_ciphertexts' for m in metrics for t in m['message_trace'])
 _,restart=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
 result=dict(status='PASS_ACTUAL_PUBLISHED_TRAINED_MODEL_SCORES_AND_SECRET_PROBABILITY',route=route,activation=activation,session=sid,source_training_session=pub_report['source_training_session'],publication_session=pub_report['session'],model=model,own_persisted_files_transferred_without_reconstruction=True,offline_completed_before_model_and_inputs_written=True,key_ids=pub['key_ids'] if route=='he' else [],servers=metrics,offline=offline,offline_seconds=offline_seconds,wall_seconds=wall,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],he_setup=setup if route=='he' else None,he_oracle=audits,official_phase_checks=checks,restored_verifier_traces=restored,classification_equal=pub_report['classification_equal'],probability_error=pub_report['probability_error'],restart_errors=[m['error'] for m in restart])
 (output_directory/f'{route}-{activation}.json').write_text(json.dumps(result,indent=2)+'\n');return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--reuse-current-publication',action='store_true');parser.add_argument('--faults',action='store_true');args=parser.parse_args()
 if not args.reuse_current_publication:
  for file in ['training.py','publication.py']:
   with (OUT/(file+'.log')).open('w') as log:subprocess.run([sys.executable,str(ROOT/'verification'/file),'--indexed'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
 publication=json.loads((ROOT/'results/continuation/publication-indexed.json').read_text());runs=[run(publication,route,activation) for activation in ('boolean','fss') for route in ('shared','he')]
 assert all(r['restored_verifier_traces']==runs[0]['restored_verifier_traces'] for r in runs)
 faults=[run(publication,'he','boolean',f) for f in ['checkpoint','scale','parameter','exhaustion','disconnect']] if args.faults else []
 result=dict(status='PASS_TRAIN_PUBLISH_PROTECTED_HE_PROBABILITY_FIVE_NODE_CHAIN',source_training_session=publication['source_training_session'],publication_session=publication['session'],model_id=publication['models'][-1]['model_id'],same_model_and_inputs_bitwise_all_six_trace_groups=True,runs=[{k:v for k,v in r.items() if k not in ('servers','restored_verifier_traces')} for r in runs],faults=faults)
 (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
