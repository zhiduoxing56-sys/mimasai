"""Independent test owner/verifier. Only this process reconstructs test traces."""
import argparse
import copy
import hashlib
import json
import os
import secrets
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT, VERSION, settings, private_write, public_descriptor, Channel
from src.he import binary_write, file_hash, native
from src.reference import Fixed, graph, config
from verification.stage2 import launch
C=config();OUT=ROOT/'results/stage3';OUT.mkdir(exist_ok=True)
MOD=1<<C['ring_bits'];WIDTH=C['model_reference']['hidden_width']

def fixture(n):
    if n==C['graph_reference']['nodes']:
        inp=json.loads((ROOT/'results/stage1/quantized-inputs.json').read_text());trace=json.loads((ROOT/'results/stage1/fixed-transform-first.json').read_text())
        return inp['propagation'],trace['transform0'],C['graph_reference']['node_order'],inp
    # Small public synthetic graph. Last node isolated, duplicate edge tests sum.
    edges=[[i,i+1,1.0+(i%3)/4] for i in range(n-2)]+[[0,1,0.25]]
    g=dict(nodes=n,node_order=[f'node-{j}' for j in range(n-1)]+['isolated'],features=[[0.1]*WIDTH for _ in range(n)],undirected_edges=edges,duplicate_policy=C['graph_reference']['duplicate_policy'],self_loop_policy=C['graph_reference']['self_loop_policy'])
    _,_,p=graph(g);fixed=Fixed(C)
    t=[[((i+1)*(j+3)*19%801)-400 for j in range(WIDTH)] for i in range(n)]
    return fixed.encode(p),[[v%MOD for v in row] for row in t],g['node_order'],None

def bundle(n):
    pp,tt,order,inputs=fixture(n);sid=secrets.token_hex(16);d=ROOT/'build/stage3'/sid
    for role in ('S0','S1','V'):(d/role).mkdir(parents=True,mode=0o700)
    binary_write(d/'V/propagation.bin',struct.pack('<'+'I'*(n*n),*[v for row in pp for v in row]))
    degree=C['he_execution_degree'];start=time.perf_counter()
    setup=native(['setup',d,degree,C['ring_bits'],*C['he_coefficient_bits'],n,WIDTH]);setup['wall_seconds']=time.perf_counter()-start
    public=dict(package_id=secrets.token_hex(16),key_ids=[file_hash(d/f'S{r}/eval.pk')[:32] for r in (0,1)],parameters_id=file_hash(d/'S0/parameters.seal'),degree=degree,ring_bits=C['ring_bits'],shape=[n,WIDTH],node_order=order,column_order=[f'hidden-{j}' for j in range(WIDTH)],input_scale=1<<C['fraction_bits'],output_scale=1<<(2*C['fraction_bits']))
    assert public['key_ids'][0]!=public['key_ids'][1]
    for role in (0,1):
        own=d/f'S{role}';files=['eval.pk','eval.gk','peer.sk','parameters.seal']+[f'rows/{i}.ct' for i in range(n)]
        private_write(own/'he.json',dict(role=role,public=public,local_integrity={p:file_hash(own/p) for p in files}))
        assert not (own/'self.sk').exists()
        assert (own/'peer.sk').read_bytes()==(d/f'V/key{1-role}.sk').read_bytes()
    return d,sid,public,setup,pp,tt,inputs

def prepare(n,activation='boolean',end_to_end=False):
    d,sid,public,setup,pp,tt,inputs=bundle(n);f=C['fraction_bits'];k=C['mpc']['activation_range_bits'];fixed=Fixed(C);z=fixed.mul(pp,tt,'verified_he_dot');raw=[[sum(fixed.signed(pp[i][j])*fixed.signed(tt[j][c]) for j in range(n))%MOD for c in range(WIDTH)] for i in range(n)];h=[[max(0,fixed.signed(v)) for v in row] for row in z]
    expected=[];plan=[];values=[]
    if end_to_end:
        assert inputs is not None
        plan.append(dict(type='matmul',dims=[n,len(inputs['weights'][0]),WIDTH],fraction=f));values.append({'x':[v for row in inputs['features'] for v in row],'y':[v for row in inputs['weights'][0] for v in row]});expected.append([v for row in tt for v in row])
    plan.append(dict(type='he_aggregate',conversion='legacy_ciphertext',count=n*WIDTH,fraction=f,k=k,activation=activation,he=public,use_previous=end_to_end));values.append({'x':[] if end_to_end else [v for row in tt for v in row]});expected.append([v for rows in (raw,z,h) for row in rows for v in row])
    private_write(d/'public-plan.json',dict(session=sid,bits=C['ring_bits'],plan=plan))
    start=time.perf_counter();p=subprocess.run([sys.executable,'-m','src.offline',str(d),str(d/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True);offline=json.loads(p.stdout);offline['wall_seconds']=time.perf_counter()-start
    jobs=[[],[]]
    for op,value in zip(plan,values):
        docs=[copy.deepcopy(op) for _ in (0,1)]
        for key,vv in value.items():
            s=[secrets.randbits(32) for _ in vv];shares=[s,[(v-a)%MOD for v,a in zip(vv,s)]]
            for r in (0,1):docs[r][key]=shares[r]
        for r in (0,1):jobs[r].append(docs[r])
    for r in (0,1):private_write(d/f'S{r}/input.json',dict(version=VERSION,session=sid,role=r,bits=C['ring_bits'],operations=jobs[r]))
    return dict(directory=d,session=sid,setup=setup,offline=offline,expected=expected,propagation=pp,transform=tt,overflow_audit=fixed.audit,public=public)

def oracle(d,role,path,own=None):
    target=d/'V/oracle-output.bin'
    result=native(['oracle',own or d/f'S{role}',d/f'V/key{role}.sk',path,target]);values=list(struct.unpack('<'+'I'*C['he_execution_degree'],target.read_bytes()));target.unlink();return values,result['noise_bits']

def check_he(item):
    d=item['directory'];n,cols=item['public']['shape'];degree=item['public']['degree'];pp=item['propagation'];t=item['transform'];stages={k:[] for k in ('encrypted_neighbor','multiply','extract','packed','masked')};padding=0;masked_nonzero=0
    for r in (0,1):
        own=d/f'S{r}'/item.get('he_slot','');xs=list(struct.unpack('<'+'I'*(n*cols),(own/'features.bin').read_bytes()));masks=list(struct.unpack('<'+'I'*(degree*cols),(own/'masks.bin').read_bytes()))
        for i in range(n):
            values,noise=oracle(d,r,own/f'rows/{i}.ct',own);stages['encrypted_neighbor'].append(noise)
            assert values[0]==pp[i][0]
            for j in range(1,n):assert values[degree-j]==(-pp[i][j])%MOD
            assert all(v==0 for v in values[1:degree-n+1]);padding+=degree-n
        for col in range(cols):
            expected=[sum(pp[i][j]*xs[j*cols+col] for j in range(n))%MOD for i in range(n)]
            for i in range(n):
                values,noise=oracle(d,r,own/f'trace/{col}_{i}_multiply.ct',own);stages['multiply'].append(noise);assert values[0]==expected[i]
                values,noise=oracle(d,r,own/f'trace/{col}_{i}_extract.ct',own);stages['extract'].append(noise);assert values[0]==expected[i] and not any(values[1:])
            values,noise=oracle(d,r,own/f'trace/{col}_packed.ct',own);stages['packed'].append(noise);assert values[:n]==expected and not any(values[n:])
            values,noise=oracle(d,r,own/f'send/{col}.ct',own);stages['masked'].append(noise)
            for j in range(degree):
                assert values[j]==((expected[j] if j<n else 0)-masks[col*degree+j])%MOD
            masked_nonzero+=sum(v!=0 for v in values[n:])
    assert all(min(v)>0 for v in stages.values())
    # Noise is evaluated only by the independent verifier under V/key*.sk.
    return dict(noise_bits={k:dict(min=min(v),max=max(v),samples=len(v)) for k,v in stages.items()},all_masked_coefficients_verified=2*degree*cols,unused_masked_coefficients_nonzero=masked_nonzero,zero_weight_padding_coefficients_checked=padding)

def run(n,activation='boolean',end_to_end=False):
    item=prepare(n,activation,end_to_end);d=item['directory'];sid=item['session'];start=time.perf_counter();attempt,metrics=launch(d,sid,C['ring_bits']);elapsed=time.perf_counter()-start
    assert all(m['success'] for m in metrics),metrics
    outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
    for op,expected in enumerate(item['expected']):assert [(a+b)%MOD for a,b in zip(outs[0][op],outs[1][op])]==expected
    assert all(m['preprocessing']['consumed']==item['offline']['generated'] for m in metrics)
    assert metrics[0]['pid']!=metrics[1]['pid']!=os.getpid()
    for r,m in enumerate(metrics):assert all(p.startswith(f'S{r}/') for p in m['loaded_private_files'])
    audit=check_he(item)
    report=dict(nodes=n,features=WIDTH,activation=activation,end_to_end_linear=end_to_end,session=sid,status='PASS',checks=sum(map(len,item['expected'])),setup=item['setup'],offline=item['offline'],servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],wall_seconds=elapsed,he_oracle=audit,verifier_overflow_audit=item['overflow_audit'])
    (OUT/f'{n}-{activation}.json').write_text(json.dumps(report,indent=2)+'\n');return report,item

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');args=ap.parse_args();reports=[]
    for n in ([5] if args.smoke else C['he_verification_nodes']):
        for activation in ('boolean','fss'):
            print(json.dumps(dict(progress='running',nodes=n,activation=activation)),flush=True)
            report,item=run(n,activation,end_to_end=(n==5));reports.append(report)
            print(json.dumps(dict(progress='passed',nodes=n,activation=activation,noise=report['he_oracle']['noise_bits'])),flush=True)
    (OUT/'summary.json').write_text(json.dumps(dict(status='PASS_CORRECTNESS_WITH_CIRCUIT_PRIVACY_BLOCKER',runs=reports,security_status='BLOCKED_CIPHERTEXT_VIEW_PRIVACY',limits=['All decoded coefficients masked; no ciphertext-view simulation/sanitization proof','Trusted offline and noncolluding passive servers; same-user local IPC','No shared prior-overflow guarantee; verifier fixtures only']),indent=2)+'\n')
    print(json.dumps(dict(status='PASS_CORRECTNESS_WITH_CIRCUIT_PRIVACY_BLOCKER',runs=len(reports)),indent=2))
if __name__=='__main__':main()
