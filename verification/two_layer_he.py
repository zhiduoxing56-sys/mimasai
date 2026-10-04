"""Real two-layer HE correctness path; converter ciphertext-view privacy BLOCKED."""
import copy,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage3 import C,ROOT,bundle,check_he
from verification.stage2 import launch
from src.mpc import VERSION,private_write
import secrets
OUT=ROOT/'results/continuation';OUT.mkdir(exist_ok=True)
def run(activation):
 d,sid,pub,setup,p,t,inputs=bundle(5);trace=json.loads((ROOT/'results/stage1/fixed-transform-first.json').read_text());f=C['fraction_bits'];n=len(p);h=C['model_reference']['hidden_width'];classes=C['model_reference']['classes']
 pub2=copy.deepcopy(pub);pub2['shape']=[n,classes];pub2['column_order']=[f'class-{j}' for j in range(classes)]
 for r in (0,1):
  own=d/f'S{r}';a=own/'he-layer0';a.mkdir(mode=0o700)
  for name in ['parameters.seal','eval.pk','eval.gk','peer.sk','rows','he.json']:(own/name).rename(a/name)
  b=own/'he-layer1';b.mkdir(mode=0o700);(b/'rows').mkdir(mode=0o700)
  for name in ['parameters.seal','eval.pk','eval.gk','peer.sk']+[f'rows/{j}.ct' for j in range(n)]:os.link(a/name,b/name)
  manifest=json.loads((a/'he.json').read_text());manifest['public']=pub2;private_write(b/'he.json',manifest)
 plan=[dict(type='matmul',dims=[n,len(inputs['weights'][0]),h],fraction=f),dict(type='he_aggregate',count=n*h,fraction=f,k=C['mpc']['activation_range_bits'],activation=activation,he=pub,use_previous=True,he_slot='he-layer0'),dict(type='matmul',dims=[n,h,classes],fraction=f,use_previous=True,previous_slice=[2*n*h,n*h]),dict(type='he_aggregate',count=n*classes,fraction=f,activation='none',he=pub2,use_previous=True,he_slot='he-layer1')]
 private_write(d/'public-plan.json',dict(session=sid,bits=C['ring_bits'],plan=plan))
 dealer=subprocess.run([sys.executable,'-m','src.offline',str(d),str(d/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True);offline=json.loads(dealer.stdout)
 jobs=[copy.deepcopy(plan) for _ in (0,1)]
 for r in (0,1):
  for op in jobs[r]:op['x']=[]
 for idx,key,values in [(0,'x',inputs['features']),(0,'y',inputs['weights'][0]),(2,'y',inputs['weights'][1])]:
  flat=[v for row in values for v in row];s=[secrets.randbits(32) for _ in flat]
  jobs[0][idx][key]=s;jobs[1][idx][key]=[(v-a)%(1<<32) for v,a in zip(flat,s)]
 for r in (0,1):private_write(d/f'S{r}/input.json',dict(version=VERSION,session=sid,role=r,bits=C['ring_bits'],operations=jobs[r]))
 start=time.perf_counter();attempt,metrics=launch(d,sid,C['ring_bits']);assert all(m['success'] for m in metrics),metrics
 outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
 restored=[[(a+b)%(1<<32) for a,b in zip(x,y)] for x,y in zip(*outs)]
 flatten=lambda a:[v for row in a for v in row]
 assert restored[0]==flatten(trace['transform0']);assert restored[1][-n*h:]==flatten(trace['hidden']);assert restored[2]==flatten(trace['transform1']);assert restored[3][-n*classes:]==flatten(trace['logits'])
 assert all(m['preprocessing']['consumed']==offline['generated'] for m in metrics)
 elapsed=time.perf_counter()-start
 audits=[check_he(dict(directory=d,public=public,propagation=p,transform=trace[key],he_slot=slot)) for public,key,slot in [(pub,'transform0','he-layer0'),(pub2,'transform1','he-layer1')]]
 return dict(status='PASS_TWO_LAYER_HE_CORRECTNESS_PRIVACY_BLOCKED',activation=activation,session=sid,setup=setup,offline=offline,servers=metrics,logits=restored[3][-n*classes:],wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],wall_seconds=elapsed,he_oracle=audits,privacy='BLOCKED same stage3 ciphertext-view issue; not secure converter acceptance')
def main():
 reports=[run(a) for a in ('boolean','fss')];(OUT/'two-layer-he.json').write_text(json.dumps(dict(status='PASS_CORRECTNESS_SECURITY_BLOCKED',runs=reports),indent=2)+'\n');print(json.dumps(dict(status='PASS_CORRECTNESS_SECURITY_BLOCKED',runs=len(reports),bytes=[r['wire_bytes'] for r in reports]),indent=2))
if __name__=='__main__':main()
