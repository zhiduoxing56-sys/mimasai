"""Controlled two-process activation/range/FSS/hidden-layer verification."""
import hashlib
import json
import secrets
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import session,launch,verify,negative_tests,C,ROOT
from src.fss import comparison_generate,comparison_eval
from src.reference import Fixed
from src.mpc import Channel,public_descriptor

OUT=ROOT/'results/stage2-round2';OUT.mkdir(exist_ok=True)
def signed(v,bits):return v if v<1<<(bits-1) else v-(1<<bits)
def flat(a):return [v for row in a for v in row]
def expect_relu(x,bits):return [max(0,signed(v%(1<<bits),bits)) for v in x]

def rejection(bits,values,k,name,limits=None,operation='range'):
    op=dict(type=operation,count=len(values),k=k,x=values,expected=[])
    directory,sid,dealer=session(bits,[op],limits);attempt,metrics=launch(directory,sid,bits)
    assert all(not m['success'] and m['error']=='RANGE_REJECTED' for m in metrics)
    assert not any((directory/('S'+str(role))/('output-'+attempt+'.json')).exists() for role in (0,1))
    # A rejected batch cannot be resumed, including reserved but unused FSS keys.
    _,again=launch(directory,sid,bits)
    assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in again)
    return dict(name=name,bits=bits,count=len(values),k=k,public_batch_flag=False,dealer=dealer,servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds'],restart='rejected')

def checks():
    comparisons=0
    for bits in range(1,6):
        for alpha in range(1<<bits):
            keys=comparison_generate(alpha,bits)
            # Validate structural keys contain neither alpha nor a domain-sized table.
            assert all(set(key)=={'format','bits','role','prefixes'} for key in keys)
            for x in range(1<<bits):
                assert comparison_eval(0,keys[0],x)^comparison_eval(1,keys[1],x)==int(x<alpha)
                comparisons+=1
    for _ in range(32):
        alpha=secrets.randbits(31);keys=comparison_generate(alpha,31)
        for x in [0,alpha,max(0,alpha-1),min((1<<31)-1,alpha+1),secrets.randbits(31)]:
            assert comparison_eval(0,keys[0],x)^comparison_eval(1,keys[1],x)==int(x<alpha);comparisons+=1
    results=[];small=[];failures=[];completed=None
    sizes=C['mpc']['activation_verification_sizes'];k=C['mpc']['activation_range_bits'];bound=1<<(k-1)
    for n in sizes:
        edges=[0,-1,1,-(1<<31),(1<<31)-1,-bound,bound-1,-bound-1,bound]
        values=(edges+[signed(secrets.randbits(32),32) for _ in range(n)])[:n]
        valid=([0,-bound,bound-1,-1,1]+[secrets.randbelow(2*bound)-bound for _ in range(n)])[:n]
        bits=[secrets.randbits(1) for _ in range(n)]
        ops=[dict(type='sign',count=n,x=values,expected=[int(v<0) for v in values]),dict(type='select',count=n,x=values,y=bits,expected=[v*b%(1<<32) for v,b in zip(values,bits)]),dict(type='range',count=n,k=k,x=valid,expected=[]),dict(type='relu',count=n,x=values,expected=expect_relu(values,32)),dict(type='fss_relu',count=n,k=k,x=valid,expected=expect_relu(valid,32))]
        result,completed=verify(32,ops,'cost_size_'+str(n));results.append(result)
        # Same public plan, different signs/splits: messages/consume schedule identical.
        opposite=[dict(op) for op in ops]
        opposite[0]['x']=[-1]*n;opposite[0]['expected']=[1]*n
        opposite[3]['x']=[-(1<<31)]*n;opposite[3]['expected']=[0]*n
        changed,_=verify(32,opposite,'trace_independence_'+str(n))
        assert all(a['message_trace']==b['message_trace'] for a,b in zip(result['servers'],changed['servers']))
        results.append(changed)
        for mode in ['one','multiple']:
            invalid=valid[:];invalid[0]=bound
            if mode=='multiple' and n>1:invalid[-1]=-bound-1
            bad=rejection(32,invalid,k,mode+'_invalid_'+str(n),operation='fss_relu')
            assert bad['servers'][0]['preprocessing']['consumed']['fss']==0
            # Compare shape/control trace through the public flag against a valid range-only run.
            good,_=verify(32,[dict(type='range',count=n,k=k,x=valid,expected=[])],'valid_range_'+str(n))
            assert bad['servers'][0]['message_trace']==good['servers'][0]['message_trace']
            failures.append(bad)
    # Complete 32-bit activation endpoints and random checks, different splitting.
    full=[0,-1,1,-(1<<31),-(1<<31)+1,(1<<31)-2,(1<<31)-1]+[signed(secrets.randbits(32),32) for _ in range(121)]
    for share in ['force_carry',None]:
        op=dict(type='relu',count=len(full),x=full,expected=expect_relu(full,32))
        if share:op['sharing']=share
        result,_=verify(32,[op],'full32_activation_boundaries_random');results.append(result)
    selection,_=verify(32,[dict(type='select',count=5,x=[128,-128,129,-129,0],y=[1,1,0,1,1],expected=[128,(-128)%(1<<32),0,(-129)%(1<<32),0])],'unit_bit_selection_no_rescale');results.append(selection)
    wrapped,_=verify(32,[dict(type='range',count=1,k=k,x=[1],expected=[])],'range_only_cannot_detect_prior_wrap');results.append(wrapped)
    for kcheck in [1,2,10,17,31,32]:
        lo=-(1<<(kcheck-1));hi=1<<(kcheck-1)
        good,_=verify(32,[dict(type='range',count=4,k=kcheck,x=[lo,hi-1,0,-1],expected=[])],'range_endpoints_'+str(kcheck));results.append(good)
        if kcheck<32:
            for val in [lo-1,hi]:failures.append(rejection(32,[val],kcheck,'exclusive_boundary_'+str(kcheck)))
    # Small-ring exhaustion for ReLU and all additive splits; range identities separately exhaustive.
    for bits in C['mpc']['small_exhaustive_bits']:
        mod=1<<bits;kcheck=bits-1;lo=-(1<<(kcheck-1));hi=1<<(kcheck-1)
        values=[v for v in range(mod) for r in range(mod)]
        ops=[dict(type='relu',count=len(values),x=values,expected=expect_relu(values,bits))]
        directory,sid,offline=session(bits,ops)
        for role in (0,1):
            path=directory/('S'+str(role))/'input.json';doc=json.loads(path.read_text())
            doc['operations'][0]['x']=[r if role==0 else (v-r)%mod for v in range(mod) for r in range(mod)]
            path.write_text(json.dumps(doc))
        attempt,metrics=launch(directory,sid,bits)
        assert all(m['success'] for m in metrics)
        outputs=[json.loads((directory/('S'+str(role))/('output-'+attempt+'.json')).read_text())['shares'][0] for role in (0,1)]
        assert [(a+b)%mod for a,b in zip(*outputs)]==expect_relu(values,bits)
        for v in range(mod):
            eq=all((v>>j)&1==(v>>(kcheck-1))&1 for j in range(kcheck,bits))
            assert eq==(lo<=signed(v,bits)<hi)
        goodvalues=[v for v in range(mod) if lo<=signed(v,bits)<hi]
        op=dict(type='fss_relu',count=len(goodvalues),k=kcheck,x=goodvalues,expected=expect_relu(goodvalues,bits))
        fss,_=verify(bits,[op],'small_real_fss_'+str(bits))
        failures.append(rejection(bits,[hi,lo-1],kcheck,'small_range_reject_'+str(bits)))
        small.append(dict(bits=bits,all_value_split_checks=len(values),servers=metrics,fss=fss))
    # Real keys with shrink k=32 also cover the entire signed ring, not merely k=17.
    result,_=verify(32,[dict(type='fss_relu',count=7,k=32,x=full[:7],expected=expect_relu(full[:7],32))],'fss_full_signed_boundaries');results.append(result)
    inputs=json.loads((ROOT/'results/stage1/quantized-inputs.json').read_text());node_order=C['graph_reference']['node_order'];hidden=[]
    for method in ['boolean','fss']:
        oracle=Fixed(C);xx=inputs['features'];ww=inputs['weights'][0];pp=inputs['propagation']
        t=oracle.mul(xx,ww,'XW0');z=oracle.mul(pp,t,'P_T0');h=[[max(0,oracle.signed(v)) for v in row] for row in z]
        reference=json.loads((ROOT/'results/stage1/fixed-transform-first.json').read_text())
        assert t==reference['transform0'] and z==reference['activation_input'] and h==reference['hidden']
        op=dict(type='hidden',dims=[len(xx),len(ww),len(ww[0])],fraction=C['fraction_bits'],scale=1<<C['fraction_bits'],node_order=node_order,k=k,activation=method,x=flat(xx),y=flat(ww),p=flat(pp),expected=flat(t)+flat(z)+flat(h))
        run,completed=verify(32,[op],'hidden_'+method);run['reference_overflow_audit']=oracle.audit;hidden.append(run)
    regression=negative_tests(completed)
    # Fresh FSS exhaustion: range passes, then no key; batch is still burned.
    op=dict(type='fss_relu',count=1,k=k,x=[0],expected=[0]);directory,sid,_=session(32,[op],{'fss':0});_,metrics=launch(directory,sid,32)
    assert all(m['error']=='PREPROCESSING_EXHAUSTED' for m in metrics)
    _,again=launch(directory,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in again)
    # Disconnect after fresh FSS key reservation and actual masked-input exchange.
    op=dict(type='fss_relu',count=1,k=32,x=[0],expected=[0]);directory,sid,prep=session(32,[op])
    proc,sock,attempt=launch(directory,sid,32,peer=False);ch=Channel(sock,0,sid,C['mpc'])
    job=json.loads((directory/'S0/input.json').read_text());descriptor=public_descriptor(job,prep['batch'])
    assert ch.exchange(-1,'hello',[8],descriptor)==descriptor
    ch.exchange(0,'range_batch_flag',[1],[1],'bit')
    ch.exchange(0,'fss_input_mask',[1],[0],span=['fss',0,1]);sock.close();proc.communicate(timeout=15)
    mid=json.loads((directory/'S1'/('metrics-'+attempt+'.json')).read_text())
    assert not mid['success'] and mid['preprocessing']['consumed']['fss']==1
    proc,sock,attempt=launch(directory,sid,32,peer=False);proc.communicate(timeout=10);sock.close()
    restart=json.loads((directory/'S1'/('metrics-'+attempt+'.json')).read_text());assert restart['error']=='BATCH_ALREADY_RESERVED'
    fss_mid_failure=dict(error=mid['error'],consumed_keys=1,restart_error=restart['error'])
    return dict(status='PASS_LOCAL_BOOLEAN_RANGE_AND_REAL_PREFIX_DPF_FSS',comparison_key_checks=comparisons,cost_runs=results,small_exhaustive=small,range_failures=failures,hidden=hidden,previous_fault_regression=regression,fss_exhaustion=[m['error'] for m in metrics],fss_mask_disconnect=fss_mid_failure,range_not_overflow_detection={'wide_integer':(1<<32)+1,'ring_element':1,'k':k,'range_passed':True},security_scope='Passive trusted offline model; PRG-based computational FSS, no constant-time/audited deployment claim')

def main():
    report=checks()
    for item in json.loads((ROOT/'results/material-manifest.json').read_text()):assert hashlib.sha256((ROOT/'参考资料'/item['file']).read_bytes()).hexdigest()==item['sha256']
    (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],real_key_checks=report['comparison_key_checks'],small_relu_checks=sum(x['all_value_split_checks'] for x in report['small_exhaustive']),range_rejected_batches=len(report['range_failures']),hidden_paths=[x['name'] for x in report['hidden']],previous_faults=len(report['previous_fault_regression'])),indent=2))
if __name__=='__main__':main()
