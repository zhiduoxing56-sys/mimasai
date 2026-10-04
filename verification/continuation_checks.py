"""Targeted numeric safety, loss/convergence, and interface regression checks."""
import copy,json,math,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import C,ROOT,verify,session,launch
from src.operators import CostCounter,bounded_matrix
from src.mpc import ProtocolError
from src.model import binding,validate,load
from src.numerical import probability_reference
OUT=ROOT/'results/continuation'
def fail_case(name,op,code):
 d,s,_=session(32,[op]);a,m=launch(d,s,32);assert not any(x['success'] for x in m) and any(x['error']==code for x in m),(name,m);_,r=launch(d,s,32);assert all(x['error']=='BATCH_ALREADY_RESERVED' for x in r);return dict(name=name,errors=[x['error'] for x in m],restarts=[x['error'] for x in r])
def main():
 f=C['training_reference']['fraction_bits'];s=1<<f;rows=[[s,0],[3*s//4,s//4],[s//4,3*s//4],[s//2,s//2],[0,s]];labels=[[s,0]]*5;mask=[True]*4+[False];terms=[]
 for row in rows[:4]:
  v=s-row[0];power=v;value=0
  for j in range(1,C['approximation']['log_degree']+1):
   value+=power*(s//j)//s
   if j<C['approximation']['log_degree']:power=power*v//s
  terms.append(value)
 base=dict(type='loss',count=10,dims=[5,2],fraction=f,training_mask=mask,x=[v for row in rows for v in row],y=[v for row in labels for v in row],expected=[sum(terms)//4]);loss,_=verify(32,[base],'secret_loss_polynomial')
 cases=[];bad=copy.deepcopy(base);bad['x'][0]=s//4-1;bad['x'][1]=s-bad['x'][0];cases.append(fail_case('loss_below_domain',bad,'LOSS_PROBABILITY_DOMAIN'))
 bad=copy.deepcopy(base);bad['y'][1]=s;cases.append(fail_case('two_hot_label',bad,'LABEL_ONE_HOT_DOMAIN'))
 bad=copy.deepcopy(base);bad['x'][0]=-1;cases.append(fail_case('negative_probability',bad,'PROBABILITY_VALUE_DOMAIN'))
 vals=[-2048,-1,0,1,2047];scaled,_=verify(32,[dict(type='precision_up',count=len(vals),source_fraction=7,fraction=12,x=vals,expected=[v*32 for v in vals])],'same_ring_scale_increase')
 cases.append(fail_case('scale_input_range',dict(type='precision_up',count=2,source_fraction=7,fraction=12,x=[0,2048],expected=[]),'RANGE_REJECTED'))
 # Public proof rejects before doing any multiplication, including a dot whose
 # encoded raw sum would wrap even though its post-wrap range could appear valid.
 unsafe=[]
 for dims,bounds in [([1,2,1],[16,16]),([5,32,3],[14,16])]:
  try:bounded_matrix(CostCounter(32),[0]*(dims[0]*dims[1]),[0]*(dims[1]*dims[2]),dims,12,*bounds)
  except ProtocolError as e:assert e.code=='PUBLIC_DOT_BOUND_UNSAFE';unsafe.append(dict(dims=dims,bounds=bounds,error=e.code))
  else:raise AssertionError('unsafe public bound accepted')
 # Real pre-multiplication operand guard rejects; no raw product released.
 cases.append(fail_case('pre_dot_operand',dict(type='bounded_matmul',dims=[1,1,1],fraction=7,bounds=[9,10],x=[-257],y=[128],expected=[]),'RANGE_REJECTED'))
 conv=[]
 for prev,current,run,threshold,window,it,maxit in [(10,9,2,1,3,2,9),(10,8,2,1,3,2,9),(10,10,1,1,3,3,9),(10,7,0,1,3,9,9)]:
  valid=int(abs(prev-current)<=threshold);next_run=valid*(run+1);stop=int(next_run>=window or it>=maxit);conv.append(dict(type='convergence',count=1,x=[prev],y=[current],p=[run],threshold=threshold,window=window,iteration=it,maximum=maxit,open_stop=True,expected=[next_run,stop]))
 convergence,_=verify(32,conv,'convergence_public_stop')
 assert [o['components'][0]['flag'] for o in convergence['servers'][0]['operations']]==[o['expected'][-1] for o in conv]
 # Different private index choices have identical logical transport trace.
 lookup=[]
 for ids in ([0,4,1,3],[3,1,0,4]):
  r,_=verify(32,[dict(type='gather',count=4,dims=[5,2],x=ids,y=list(range(10)),expected=[v for i in ids for v in [2*i,2*i+1]])],'index_trace');lookup.append(r)
 assert lookup[0]['servers'][0]['message_trace']==lookup[1]['servers'][0]['message_trace']
 grids=[]
 for ff in (7,12):
  ss=1<<ff;inputs=[[0,d] for d in range(-8*ss,1)];ref,_=probability_reference(inputs,ff);maxerr=max(abs(a/ss-(1/(1+math.exp((row[1]-row[0])/ss)) if j==0 else 1/(1+math.exp((row[0]-row[1])/ss)))) for row,values in zip(inputs,ref) for j,a in enumerate(values));grids.append(dict(fraction_bits=ff,negative_gap_integer_grid=len(inputs),max_error=maxerr,scope='plaintext approximation error grid, not additional MPC tests'))
 # Reference-only persistence faults: values stay in a private test directory.
 model=binding(secrets.token_hex(16),C['graph_reference']['node_order'],2,3,2,7)
 folder=ROOT/'build/continuation-model-checks'/secrets.token_hex(16);folder.mkdir(parents=True,mode=0o700)
 path=folder/'own-model.json';from src.mpc import private_write
 stored=dict(version='additive-model-v1',role=0,binding=model,shares=[0]*12)
 private_write(path,stored);assert load(0,path,model)==[0]*12
 model_faults=[]
 for name,change,code in [('role',{'role':1},'MODEL_LOAD_BINDING'),('shape',{'shares':[0]*11},'MODEL_LOAD_SHARES'),('residue',{'shares':[-1]+[0]*11},'MODEL_LOAD_SHARES')]:
  altered=copy.deepcopy(stored);altered.update(change);fault_path=folder/(name+'.json');private_write(fault_path,altered)
  try:load(0,fault_path,model)
  except ProtocolError as err:assert err.code==code;model_faults.append(dict(name=name,error=err.code))
  else:raise AssertionError(name)
 for field,value in [('bias','trainable'),('probability_fraction_bits',7),('model_version','other')]:
  altered=copy.deepcopy(model);altered[field]=value
  try:load(0,path,altered)
  except ProtocolError as err:assert err.code=='MODEL_CONFIG_BINDING';model_faults.append(dict(name=field,error=err.code))
  else:raise AssertionError(field)
 altered=copy.deepcopy(model);altered['node_order']=list(reversed(altered['node_order']))
 try:load(0,path,altered)
 except ProtocolError as err:assert err.code=='MODEL_LOAD_BINDING';model_faults.append(dict(name='node_order',error=err.code))
 else:raise AssertionError('node_order')
 # Servers cannot read verifier fixtures, even after successfully reserving a batch.
 runtime=json.loads((ROOT/'config/phase0.json').read_text())
 assert not any(k in runtime['model_reference'] for k in ['initial_weights','labels'])
 assert not any(k in runtime['graph_reference'] for k in ['undirected_edges','features'])
 dd,ss,_=session(32,[dict(type='add',count=1,x=[1],y=[2],expected=[3])]);_,view=launch(dd,ss,32,worker='verification.reference_view_fault_worker')
 assert all(m['error']=='REFERENCE_DATA_VIEW_VIOLATION' and not m['success'] for m in view)
 _,replay=launch(dd,ss,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in replay)
 view_check=dict(runtime_config_contains_plaintext_inputs=False,errors=[m['error'] for m in view],restarts=[m['error'] for m in replay])
 # Clear continuous derivative evidence, separate from secret correctness.
 z=[0.0,-0.5]
 def smooth_prob(v):
  d=[(t-max(v))/16 for t in v];ex=[(1+t+t*t/2)**16 for t in d];return [t/sum(ex) for t in ex]
 def smooth_loss(v):
  q=smooth_prob(v)[1];return sum((1-q)**j/j for j in range(1,9))
 pp=smooth_prob(z);exact=[]
 for j in range(2):
  aa=z[:];bb=z[:];aa[j]+=1e-6;bb[j]-=1e-6;exact.append((smooth_loss(aa)-smooth_loss(bb))/2e-6)
 grad_evidence=dict(logits=z,label=1,approximate_standard_gradient=[pp[0],pp[1]-1],continuous_approx_loss_numerical_gradient=exact,max_difference=max(abs(a-b) for a,b in zip(exact,[pp[0],pp[1]-1])),scope='Reference derivative evidence; fixed-point floors are not differentiated')
 (OUT/'targeted-checks.json').write_text(json.dumps(dict(status='PASS_NUMERIC_SAFETY_LOSS_CONVERGENCE',loss=loss,scale=scaled,failures=cases,public_unsafe_bounds=unsafe,convergence=convergence,index_traces=lookup,approximation_grid=grids,model_faults=model_faults,gradient_choice=grad_evidence,reference_view=view_check),indent=2)+'\n');print(json.dumps(dict(status='PASS_NUMERIC_SAFETY_LOSS_CONVERGENCE',failures=len(cases),public_rejections=len(unsafe),grids=grids),indent=2))
if __name__=='__main__':main()
