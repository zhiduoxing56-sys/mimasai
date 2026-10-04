"""Fresh sessions and offline batches; intentional fault injection by verifier."""
import copy
import json
import os
import secrets
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage3 import C, OUT, ROOT, WIDTH, prepare, check_he
from verification.stage2 import launch, verify
from src.mpc import private_write
from src.he import binary_write, native

def clone(base):
    sid=secrets.token_hex(16);d=ROOT/'build/stage3'/sid;source=base['directory']
    for r in (0,1):
        own=d/f'S{r}';own.mkdir(parents=True,mode=0o700);(own/'rows').mkdir(mode=0o700)
        for name in ['parameters.seal','eval.pk','eval.gk','peer.sk']+[f'rows/{j}.ct' for j in range(5)]:os.link(source/f'S{r}'/name,own/name)
        shutil.copyfile(source/f'S{r}/he.json',own/'he.json');os.chmod(own/'he.json',0o600)
        job=json.loads((source/f'S{r}/input.json').read_text());job['session']=sid;private_write(own/'input.json',job)
    plan=json.loads((source/'public-plan.json').read_text());plan['session']=sid;private_write(d/'public-plan.json',plan)
    import subprocess
    subprocess.run([sys.executable,'-m','src.offline',str(d),str(d/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True)
    return d,sid

def failure_tests():
    base=prepare(5,'fss');failures=[]
    for name in ['node_order','column_order','key_mismatch','parameter_mismatch','mask_duplicate','conversion_disconnect']:
        d,sid=clone(base)
        if name in ('node_order','column_order'):
            key=name
            for r in (0,1):
                path=d/f'S{r}/input.json';job=json.loads(path.read_text());job['operations'][0]['he'][key].reverse();path.write_text(json.dumps(job))
        elif name in ('key_mismatch','parameter_mismatch'):
            target=d/('S0/eval.pk' if name=='key_mismatch' else 'S0/parameters.seal');old=target.read_bytes();target.unlink()
            binary_write(target,(d/'S1/eval.pk').read_bytes() if name=='key_mismatch' else old[:-1]+bytes([old[-1]^1]))
        elif name=='mask_duplicate':
            path=d/'S0/preprocessing.json';doc=json.loads(path.read_text());doc['materials']['he_mask']=[doc['materials']['he_mask'][0]]*3;path.write_text(json.dumps(doc))
        attempt,metrics=launch(d,sid,32,worker='verification.stage3_fault_worker' if name=='conversion_disconnect' else 'src.mpc_worker')
        assert not any(m['success'] for m in metrics),(name,metrics)
        expected={'node_order':'HE_INTERFACE_BINDING','column_order':'HE_INTERFACE_BINDING','key_mismatch':'HE_LOCAL_KEY_OR_PARAMETER_BINDING','parameter_mismatch':'HE_LOCAL_KEY_OR_PARAMETER_BINDING','mask_duplicate':'HE_MASK_IDENTIFIER_REUSE','conversion_disconnect':'DISCONNECTED'}[name]
        assert any(m['error']==expected for m in metrics),(name,metrics)
        assert not any((d/f'S{r}/output-{attempt}.json').exists() for r in (0,1))
        _,restarts=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restarts)
        failures.append(dict(name=name,errors=[m['error'] for m in metrics],consumed=[m['preprocessing']['consumed'] for m in metrics],rounds=[m['communication']['exchange_rounds'] for m in metrics],restart_errors=[m['error'] for m in restarts]))
    # Same mask identifiers replayed under a fresh batch/session are rejected globally.
    source=next(x for x in json.loads((OUT/'summary.json').read_text())['runs'] if x['nodes']==5 and x['activation']=='boolean')
    old=ROOT/'build/stage3'/source['session'];d,sid=clone(base)
    path=d/'S0/preprocessing.json';doc=json.loads(path.read_text());doc['materials']['he_mask']=json.loads((old/'S0/preprocessing.json').read_text())['materials']['he_mask'];path.write_text(json.dumps(doc))
    attempt,metrics=launch(d,sid,32);assert any(m['error']=='HE_MASK_IDENTIFIER_REUSE' for m in metrics) and not any(m['success'] for m in metrics)
    failures.append(dict(name='mask_reuse_new_batch',errors=[m['error'] for m in metrics],consumed=[m['preprocessing']['consumed'] for m in metrics]))
    # Full-ring endpoints as actual local feature shares, with the other share adjusted.
    d,sid=clone(base);x=[v for row in base['transform'] for v in row];split=[0,(1<<32)-1,1<<31,(1<<31)-1]+[secrets.randbits(32) for _ in x[4:]]
    for r in (0,1):
        path=d/f'S{r}/input.json';job=json.loads(path.read_text());job['operations'][0]['x']=split if r==0 else [(v-a)%(1<<32) for v,a in zip(x,split)];path.write_text(json.dumps(job))
    attempt,metrics=launch(d,sid,32);assert all(m['success'] for m in metrics),metrics
    outs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'][0] for r in (0,1)];assert [(a+b)%(1<<32) for a,b in zip(*outs)]==base['expected'][0]
    # Key owner is verifier only; link test keys into V for coefficient/noise audits.
    (d/'V').mkdir(mode=0o700)
    for r in (0,1):os.link(base['directory']/f'V/key{r}.sk',d/f'V/key{r}.sk')
    item=dict(base,directory=d,session=sid);audit=check_he(item)
    # All-zero local operand is handled by fresh encryption of known zero, not
    # disabling SEAL transparent-ciphertext checks and not decrypt/re-encrypt.
    dz,sz=clone(base)
    for r in (0,1):
        path=dz/f'S{r}/input.json';job=json.loads(path.read_text());job['operations'][0]['x']=[0]*len(x) if r==0 else x;path.write_text(json.dumps(job))
    az,mz=launch(dz,sz,32);assert all(m['success'] for m in mz),mz
    oz=[json.loads((dz/f'S{r}/output-{az}.json').read_text())['shares'][0] for r in (0,1)];assert [(a+b)%(1<<32) for a,b in zip(*oz)]==base['expected'][0]
    (dz/'V').mkdir(mode=0o700)
    for r in (0,1):os.link(base['directory']/f'V/key{r}.sk',dz/f'V/key{r}.sk')
    zero_audit=check_he(dict(base,directory=dz,session=sz))
    return failures,dict(status='PASS',local_share_boundary_cases=4,he_oracle=audit,all_zero_local_share=dict(status='PASS',he_oracle=zero_audit))

def comparisons():
    from verification.stage3 import fixture, MOD
    from src.reference import Fixed
    results=[]
    for n in C['he_verification_nodes']:
        p,t,order,_=fixture(n);fixed=Fixed(C);z=fixed.mul(p,t,'shared_baseline');flat=[v for row in z for v in row];h=[max(0,fixed.signed(v)) for v in flat]
        plan=[dict(type='matmul',dims=[n,n,WIDTH],fraction=C['fraction_bits'],x=[v for row in p for v in row],y=[v for row in t for v in row],expected=flat),dict(type='checked_relu',count=n*WIDTH,k=C['mpc']['activation_range_bits'],x=[],use_previous=True,expected=h)]
        report,_=verify(32,plan,f'shared_matrix_{n}');results.append(report)
    return results

def main():
    faults,endpoints=failure_tests();baseline=comparisons();reports=json.loads((OUT/'summary.json').read_text())['runs'];view=[]
    for report in reports:
        d=ROOT/'build/stage3'/report['session']
        for r in (0,1):
            for col in range(WIDTH):
                result=native(['mask_audit',d/f'S{r}',d/f'S{r}/trace/{col}_packed.ct',d/f'S{r}/send/{col}.ct']);assert result['ciphertext_component_one_unchanged'];view.append(result)
    result=dict(status='PASS_FAULTS_AND_COEFFICIENT_CORRECTNESS_WITH_CIRCUIT_PRIVACY_BLOCKER',faults=faults,full_ring_share_endpoints=endpoints,shared_matrix_baseline=baseline,circuit_privacy=dict(status='BLOCKED',unchanged_c1_checks=len(view),basis='Full plaintext coefficient masks leave c1 unchanged; no ciphertext-view simulation or sanitization proof. Correctness is not full converter privacy.'))
    (OUT/'faults-and-baseline.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],faults=len(faults),baselines=len(baseline),unchanged_c1_checks=len(view)),indent=2))
if __name__=='__main__':main()
