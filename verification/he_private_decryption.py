"""Real HE + private-input BFV decryption. Recovery only by this verifier."""
import argparse,copy,json,math,os,secrets,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage3 import bundle,check_he,oracle,C,ROOT,MOD
from verification.stage2 import launch
from src.he import native
from src.he_secure import crt,read_poly
from src.mpc import VERSION,private_write
OUT=ROOT/'results/security-round';OUT.mkdir(parents=True,exist_ok=True)
def oracle_round(d,own,key,n,cols,qs):
 degree=C['he_execution_degree'];peer=d/f'S{1-key}'/own.relative_to(d/f'S{key}');secret=read_poly(peer/'peer-key-coefficients.bin',degree,qs);checks=0
 for col in range(cols):
  c0=read_poly(own/f'cipher-{col}-0.bin',degree,qs);c1=read_poly(own/f'cipher-{col}-1.bin',degree,qs);expected,_=oracle(d,key,own/f'send/{col}.ct',own)
  for row in range(n):
   residues=[]
   for l,p in enumerate(qs):
    phase=c0[l*degree+row]
    for j in range(degree):
     index=row-j;phase += c1[l*degree+j]*secret[l*degree+index%degree]*(1 if index>=0 else -1)
    residues.append(phase%p)
   phase=crt(residues,qs);q=math.prod(qs);assert ((1<<32)*phase+q//2)//q%(1<<32)==expected[row];checks+=1
 return checks

def audit_ring(d,qs):
 # Independent verifier only: recover one OFFLINE triple, direct coefficient
 # convolution, without logging any recovered material.
 degree=C['he_execution_degree'];triples=[]
 for name in ('a','b','c'):
  parts=[read_poly(d/f'S{r}/ring-preprocessing/0/{name}.bin',degree,qs) for r in (0,1)]
  triples.append([(x+y)%q for l,q in enumerate(qs) for x,y in zip(parts[0][l*degree:(l+1)*degree],parts[1][l*degree:(l+1)*degree])])
 a,b,c=triples;checks=0
 for l,q in enumerate(qs):
  for row in (0,1,degree-1):
   expected=sum(a[l*degree+j]*b[l*degree+(row-j)%degree]*(1 if row-j>=0 else -1) for j in range(degree))%q
   assert expected==c[l*degree+row];checks+=1
 return checks

def run(cols=1,two_layers=False,activation='boolean',fault=None):
 d,sid,pub,setup,p,t,inputs=bundle(5);n=len(p);public_moduli=native(['metadata',d/'S0'])['data_moduli'];pub['data_moduli']=public_moduli;pub['shape']=[n,cols];pub['column_order']=[f'column-{j}' for j in range(cols)]
 os.link(d/'S0/parameters.seal',d/'parameters.seal')
 trace=json.loads((ROOT/'results/stage1/fixed-transform-first.json').read_text());h=C['model_reference']['hidden_width'];classes=C['model_reference']['classes'];f=C['fraction_bits']
 slots=[];plan=[];jobs=[];expected=[]
 if two_layers:
  assert cols==h
  pub2=copy.deepcopy(pub);pub2['shape']=[n,classes];pub2['column_order']=[f'class-{j}' for j in range(classes)]
  slots=[('he-layer0',pub),('he-layer1',pub2)]
  plan=[dict(type='matmul',dims=[n,len(inputs['weights'][0]),h],fraction=f),dict(type='he_aggregate',count=n*h,fraction=f,k=C['mpc']['activation_range_bits'],activation=activation,conversion='private_decryption',he=pub,use_previous=True,he_slot='he-layer0'),dict(type='matmul',dims=[n,h,classes],fraction=f,use_previous=True,previous_slice=[2*n*h,n*h]),dict(type='he_aggregate',count=n*classes,fraction=f,activation='none',conversion='private_decryption',he=pub2,use_previous=True,he_slot='he-layer1')]
  expected=[trace['transform0'],trace['hidden'],trace['transform1'],trace['logits']]
 else:
  plan=[dict(type='he_aggregate',count=n*cols,fraction=f,k=C['mpc']['activation_range_bits'],activation=activation,conversion='private_decryption',he=pub)];expected=[[[max(0,sum(p[i][j]*(t[j][c] if t[j][c]<1<<31 else t[j][c]-(1<<32)) for j in range(n))//(1<<f))%MOD for c in range(cols)] for i in range(n)]]
 for role in (0,1):
  own=d/f'S{role}';doc=json.loads((own/'he.json').read_text());doc['public']=pub;(own/'he.json').write_text(json.dumps(doc))
  if two_layers:
   a=own/'he-layer0';a.mkdir(mode=0o700)
   for name in ['parameters.seal','eval.pk','eval.gk','peer.sk','rows','he.json']:(own/name).rename(a/name)
   b=own/'he-layer1';b.mkdir(mode=0o700);(b/'rows').mkdir(mode=0o700)
   for name in ['parameters.seal','eval.pk','eval.gk','peer.sk']+[f'rows/{j}.ct' for j in range(n)]:os.link(a/name,b/name)
   doc['public']=pub2;private_write(b/'he.json',doc)
 private_write(d/'public-plan.json',dict(session=sid,bits=32,plan=plan))
 started=time.monotonic();dealer=subprocess.run([sys.executable,'-m','src.offline',str(d),str(d/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True);offline=json.loads(dealer.stdout);offline_seconds=time.monotonic()-started
 jobs=[copy.deepcopy(plan) for _ in (0,1)]
 for role in (0,1):
  for op in jobs[role]:op['x']=[]
 values=[(0,'x',inputs['features']),(0,'y',inputs['weights'][0]),(2,'y',inputs['weights'][1])] if two_layers else [(0,'x',[row[:cols] for row in t])]
 for index,key,rows in values:
  flat=[v for row in rows for v in row];share=[secrets.randbits(32) for v in flat];jobs[0][index][key]=share;jobs[1][index][key]=[(v-a)%MOD for v,a in zip(flat,share)]
 for role in (0,1):private_write(d/f'S{role}/input.json',dict(version=VERSION,session=sid,role=role,bits=32,operations=jobs[role]))
 if fault=='context':
  file=d/'S0/he.json';doc=json.loads(file.read_text());doc['public']['data_moduli'][0]-=2;file.write_text(json.dumps(doc))
 elif fault=='ring_residue':
  file=d/'S0/ring-preprocessing/0/c.bin'
  raw=bytearray(file.read_bytes());raw[:8]=(public_moduli[0]).to_bytes(8,'little');file.write_bytes(raw)
 if fault:
  _,metrics=launch(d,sid,32,worker='verification.he_private_fault_worker' if fault=='disconnect' else 'src.mpc_worker',timeout=240)
  assert not any(m['success'] for m in metrics),(fault,metrics)
  _,restart=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
  # Retaining the consumed/reserved ring IDs in a different batch is refused.
  new_id='replay-'+secrets.token_hex(12)
  for role in (0,1):
   file=d/f'S{role}/preprocessing.json';doc=json.loads(file.read_text());doc['batch']=new_id;file.write_text(json.dumps(doc))
  _,new_batch=launch(d,sid,32);assert all(m['error']=='RING_MATERIAL_REUSE' for m in new_batch)
  result=dict(status='PASS_FAILURE_BURN_AND_REUSE_REJECTION',fault=fault,session=sid,errors=[m['error'] for m in metrics],restart_errors=[m['error'] for m in restart],new_batch_errors=[m['error'] for m in new_batch]);(OUT/('he-private-fault-'+fault+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
 started=time.monotonic();attempt,metrics=launch(d,sid,32,timeout=240);wall=time.monotonic()-started;assert all(m['success'] for m in metrics),metrics
 outputs=[json.loads((d/f'S{role}/output-{attempt}.json').read_text())['shares'] for role in (0,1)]
 for i,rows in enumerate(expected):
  restored=[(a+b)%MOD for a,b in zip(outputs[0][i],outputs[1][i])];flat=[v for row in rows for v in row];assert restored[-len(flat):]==flat,(i,restored[-len(flat):],flat)
 assert all(m['preprocessing']['consumed']==offline['generated'] for m in metrics)
 assert all(m['pid']!=os.getpid() for m in metrics) and metrics[0]['pid']!=metrics[1]['pid']
 for m in metrics:
  assert not any(x['type']=='he_masked_ciphertexts' for x in m['message_trace'])
  assert all(x.startswith(f'S{m["role"]}/') for x in m['loaded_private_files'])
 ring_checks=audit_ring(d,public_moduli)
 audits=[];round_checks=0
 for slot,public in (slots if two_layers else [('',pub)]):
  audits.append(check_he(dict(directory=d,public=public,propagation=p,transform=t,he_slot=slot)))
  for key in (0,1):round_checks+=oracle_round(d,d/f'S{key}'/slot,key,n,public['shape'][1],public_moduli)
 # Same reserved batch cannot be re-entered after success.
 _,replay=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in replay)
 result=dict(status='PASS_REAL_HE_PRIVATE_DECRYPTION_COMPOSED_PASSIVE_PROTOCOL',session=sid,activation=activation,columns=cols,two_layers=two_layers,servers=metrics,offline=offline,offline_seconds=offline_seconds,wall_seconds=wall,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],oracle_round_checks=round_checks,ring_triple_coefficient_checks=ring_checks,he_oracle=audits,key_ids=pub['key_ids'],setup=setup,replay_errors=[m['error'] for m in replay],security_basis='Private-input ideal decryption realized by trusted-offline Beaver polynomial ring multiplication + secret exact carry rounding; no peer evaluated ciphertext/phase/error is revealed',limits=['Passive only, trusted offline and valid key setup, application view audit not OS isolation','Not ciphertext sanitization/randomized BFV reproduction; extra interaction','HE input fixtures checked by verifier for pre-truncation integer range'])
 filename='he-private-'+('two-layer' if two_layers else f'{cols}-columns')+'-'+activation+'.json';(OUT/filename).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','session','columns','two_layers','wire_bytes','rounds','wall_seconds','oracle_round_checks']},indent=2));return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--columns',type=int,default=1);parser.add_argument('--two-layers',action='store_true');parser.add_argument('--fault',choices=['disconnect','context','ring_residue']);parser.add_argument('--activation',choices=['boolean','fss'],default='boolean');args=parser.parse_args();run(args.columns,args.two_layers,args.activation,args.fault)
