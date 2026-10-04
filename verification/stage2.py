"""Separate verifier/dealer/server processes; plaintext recovery only here."""
import copy
import hashlib
import json
import os
import secrets
import socket
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT, VERSION, Channel, ProtocolError, settings, private_write, public_descriptor
from src.reference import Fixed,config

C=config(); RESULTS=ROOT/'results/stage2'; RUNTIME=ROOT/'build/stage2'
RESULTS.mkdir(exist_ok=True); RUNTIME.mkdir(exist_ok=True)

def session(bits,plain,limits=None):
    sid=secrets.token_hex(16); directory=RUNTIME/sid
    for role in (0,1): (directory/('S'+str(role))).mkdir(parents=True,mode=0o700)
    plan=[]
    for op in plain:
        plan.append({k:v for k,v in op.items() if k not in ('x','y','p','labels','indices','edge_weights','expected','sharing')})
    private_write(directory/'public-plan.json',dict(session=sid,bits=bits,plan=plan,limits=limits))
    # Offline process completes before online input files even exist.
    offline_started=time.perf_counter()
    dealer=subprocess.run([sys.executable,'-m','src.offline',str(directory),str(directory/'public-plan.json')],cwd=ROOT,capture_output=True,text=True,check=True)
    generated=json.loads(dealer.stdout);generated['offline_wall_seconds']=time.perf_counter()-offline_started
    jobs=[[],[]];mod=1<<bits
    for op in plain:
        docs=[{k:v for k,v in op.items() if k not in ('x','y','p','labels','indices','edge_weights','expected','sharing')} for _ in range(2)]
        for name in ('x','y','p','labels','indices','edge_weights'):
            if name not in op: continue
            values=[v%mod for v in op[name]]
            aa=[secrets.randbelow(mod) for _ in values]
            if op.get('sharing')=='force_carry': aa=[mod-1]*len(values)
            bb=[(v-a)%mod for v,a in zip(values,aa)]
            for role,shares in enumerate([aa,bb]):docs[role][name]=shares
        for role in (0,1): jobs[role].append(docs[role])
    for role in (0,1):private_write(directory/('S'+str(role))/'input.json',dict(version=VERSION,session=sid,role=role,bits=bits,operations=jobs[role]))
    return directory,sid,generated

def launch(directory,sid,bits,peer=True,mutate=None,worker='src.mpc_worker',timeout=30):
    s0,s1=socket.socketpair();attempt=secrets.token_hex(8); procs=[]
    if mutate: mutate(directory)
    if peer:
        for role,sock in [(0,s0),(1,s1)]:
            procs.append(subprocess.Popen([sys.executable,'-m',worker,str(role),str(directory),sid,str(bits),str(sock.fileno()),attempt],cwd=ROOT,pass_fds=(sock.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
        s0.close();s1.close()
        logs=[p.communicate(timeout=timeout) for p in procs]
        assert all(not err for out,err in logs), 'worker unexpected stderr'
        metrics=[json.loads((directory/('S'+str(role))/('metrics-'+attempt+'.json')).read_text()) for role in (0,1)]
    else:
        proc=subprocess.Popen([sys.executable,'-m',worker,'1',str(directory),sid,str(bits),str(s1.fileno()),attempt],cwd=ROOT,pass_fds=(s1.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        s1.close(); return proc,s0,attempt
    return attempt,metrics

def verify(bits,plain,name):
    directory,sid,offline=session(bits,plain);attempt,metrics=launch(directory,sid,bits)
    assert all(m['success'] for m in metrics),metrics
    assert all(m['loaded_private_files']==['S'+str(m['role'])+'/preprocessing.json','S'+str(m['role'])+'/input.json'] for m in metrics)
    assert metrics[0]['pid']!=metrics[1]['pid'] and all(m['pid']!=os.getpid() for m in metrics)
    outs=[json.loads((directory/('S'+str(role))/('output-'+attempt+'.json')).read_text())['shares'] for role in (0,1)]
    mod=1<<bits;checks=0
    for idx,op in enumerate(plain):
        recovered=[(a+b)%mod for a,b in zip(outs[0][idx],outs[1][idx])]
        assert recovered==[v%mod for v in op['expected']],(name,idx)
        checks+=len(recovered)
    assert metrics[0]['communication']['bytes_sent']==metrics[1]['communication']['bytes_received']
    assert metrics[0]['communication']['exchange_rounds']==metrics[1]['communication']['exchange_rounds']
    assert metrics[0]['preprocessing']['consumed']==offline['generated']==metrics[1]['preprocessing']['consumed']
    return {'name':name,'bits':bits,'checks':checks,'session':sid,'dealer':offline,'servers':metrics,'wire_bytes':sum(m['communication']['bytes_sent'] for m in metrics),'exchange_rounds':metrics[0]['communication']['exchange_rounds']},(directory,sid,bits)

def trunc_expected(values,bits,f):
    mod=1<<bits;return [((v%mod if v%mod<mod//2 else v%mod-mod)//(1<<f))%mod for v in values]

def full_tests():
    bits=C['ring_bits'];f=C['fraction_bits'];mod=1<<bits
    vals=[-mod//2,-mod//2+1,mod//2-2,mod//2-1,0,1,-1]
    for multiple in [-257,-2,-1,0,1,2,257]: vals += [multiple*(1<<f)+offset for offset in [-1,0,1]]
    vals += [secrets.randbelow(mod) for _ in range(C['mpc']['random_verification_samples'])]
    xx=[0,1,-1,127,-128,129,-129,1024,-1024,mod-1]
    yy=[-1,mod-1,1,-128,127,-1,1,-128,128,1]
    for u,v in zip(xx,yy):
        su=u%mod if u%mod<mod//2 else u%mod-mod
        sv=v%mod if v%mod<mod//2 else v%mod-mod
        assert -mod//2<=su*sv<mod//2
    plain=[dict(type='add',count=len(xx),x=xx,y=yy,expected=[(a+b)%mod for a,b in zip(xx,yy)],sharing='force_carry'),dict(type='sub',count=len(xx),x=xx,y=yy,expected=[(a-b)%mod for a,b in zip(xx,yy)]),dict(type='public_mul',count=len(xx),x=xx,scalar=-3,expected=[a*(-3)%mod for a in xx]),dict(type='mul',count=len(xx),x=xx,y=yy,expected=[a*b%mod for a,b in zip(xx,yy)]),dict(type='truncate',count=len(vals),fraction=f,x=vals,expected=trunc_expected(vals,bits,f),sharing='force_carry')]
    # Stage-one trained weights used only by the verifier; dealer sees dimensions.
    inputs=json.loads((ROOT/'results/stage1/quantized-inputs.json').read_text())
    matrices=[([[127,-129,256],[-128,129,-255]],[[128,-128],[-129,127],[64,-65]])]
    matrices.append((inputs['features'],inputs['weights'][0]))
    for a,b in matrices:
        oracle=Fixed(C);out=oracle.mul(a if all(0<=v<mod for row in a for v in row) else [[v%mod for v in row] for row in a],b if all(0<=v<mod for row in b for v in row) else [[v%mod for v in row] for row in b],'verifier_dot')
        plain.append(dict(type='matmul',dims=[len(a),len(b),len(b[0])],fraction=f,x=[v for row in a for v in row],y=[v for row in b for v in row],expected=[v for row in out for v in row]))
    result,completed=verify(bits,plain,'ring32_boundaries_random_and_stage1_dot')
    return result,completed

def small_tests():
    results=[]
    for bits in C['mpc']['small_exhaustive_bits']:
        # All possible local-share pairs: every value with every additive split.
        mod=1<<bits;f=min(2,bits-1);xx=[v for v in range(mod) for _ in range(mod)]
        plain=[dict(type='truncate',count=len(xx),fraction=f,x=xx,expected=trunc_expected(xx,bits,f))]
        directory,sid,offline=session(bits,plain)
        for role in (0,1):
            path=directory/('S'+str(role))/'input.json';doc=json.loads(path.read_text())
            shares=[r if role==0 else (v-r)%mod for v in range(mod) for r in range(mod)]
            doc['operations'][0]['x']=shares;path.write_text(json.dumps(doc))
        attempt,metrics=launch(directory,sid,bits)
        assert all(m['success'] for m in metrics),metrics
        outputs=[json.loads((directory/('S'+str(role))/('output-'+attempt+'.json')).read_text())['shares'][0] for role in (0,1)]
        assert [(a+b)%mod for a,b in zip(*outputs)]==plain[0]['expected']
        assert all(m['preprocessing']['consumed']==offline['generated'] for m in metrics)
        results.append(dict(name='all_values_all_additive_splits',bits=bits,fraction=f,checks=len(xx),dealer=offline,servers=metrics,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),exchange_rounds=metrics[0]['communication']['exchange_rounds']))
    return results

def negative_tests(completed):
    failures=[];directory,sid,bits=completed
    _,metrics=launch(directory,sid,bits)
    assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in metrics)
    failures.append(dict(name='completed_batch_replay',errors=[m['error'] for m in metrics]))
    op=dict(type='mul',count=1,x=[128],y=[-129],expected=[128*(-129)%(1<<32)])
    for name,limits in [('exhaustion',{'arithmetic':0}),('shape',None),('session',None),('schedule',None)]:
        directory,sid,_=session(32,[op],limits)
        if name in ('shape','session','schedule'):
            path=directory/'S1/input.json';doc=json.loads(path.read_text())
            if name=='shape':doc['operations'][0]['x']=[]
            elif name=='session':doc['session']=secrets.token_hex(16)
            else:doc['operations'][0]['count']=2
            path.write_text(json.dumps(doc))
        _,metrics=launch(directory,sid,32)
        assert not any(m['success'] for m in metrics)
        assert any(m['error']=={'exhaustion':'PREPROCESSING_EXHAUSTED','shape':'INPUT_SHAPE','session':'INPUT_BINDING','schedule':'PUBLIC_SCHEDULE_MISMATCH'}[name] for m in metrics)
        failures.append(dict(name=name,errors=[m['error'] for m in metrics]))
    for name in ['disconnect','timeout','wire_shape','wire_session','wire_order','wire_length','wire_actual_length']:
        directory,sid,_=session(32,[op]);proc,sock,attempt=launch(directory,sid,32,peer=False)
        if name=='disconnect': sock.close()
        elif name=='timeout': pass
        else:
            ch=Channel(sock,0,sid,C['mpc'])
            job=json.loads((directory/'S0/input.json').read_text());batch=json.loads((directory/'S0/preprocessing.json').read_text())['batch']
            descriptor=public_descriptor(job,batch);frame,header=ch.frame(-1,'hello',[8],descriptor,'u32',None)
            if name=='wire_shape':header['shape']=[2]
            elif name=='wire_session':header['session']=secrets.token_hex(16)
            elif name=='wire_order':header['sequence']=9
            elif name=='wire_length':header['payload_length']=36
            raw=json.dumps(header,separators=(',',':')).encode();body=struct.pack('!I',len(raw))+raw+struct.pack('<8I',*descriptor)
            if name=='wire_actual_length': body=body[:-4]
            sock.sendall(struct.pack('!I',len(body))+body)
        stdout,stderr=proc.communicate(timeout=15);sock.close()
        assert not stderr
        metric=json.loads((directory/'S1'/('metrics-'+attempt+'.json')).read_text())
        assert not metric['success'] and metric['error']==({'disconnect':'DISCONNECTED','timeout':'TIMEOUT','wire_actual_length':'PAYLOAD_LENGTH'}.get(name,'MESSAGE_METADATA'))
        # Restart is a new process with unchanged durable ledger and same material.
        proc,sock,attempt=launch(directory,sid,32,peer=False);stdout,stderr=proc.communicate(timeout=10);sock.close()
        restart=json.loads((directory/'S1'/('metrics-'+attempt+'.json')).read_text())
        assert restart['error']=='BATCH_ALREADY_RESERVED'
        failures.append(dict(name=name,error=metric['error'],restart_error=restart['error'],consumed=metric['preprocessing']['consumed'],reserved=metric['preprocessing']['reserved']))
    # Kill after an actual multiplication mask exchange, then reject restart.
    directory,sid,_=session(32,[op,dict(type='truncate',count=1,fraction=7,x=[128],expected=[1])])
    proc,sock,attempt=launch(directory,sid,32,peer=False)
    ch=Channel(sock,0,sid,C['mpc'])
    job=json.loads((directory/'S0/input.json').read_text());prep=json.loads((directory/'S0/preprocessing.json').read_text())
    descriptor=public_descriptor(job,prep['batch']);assert ch.exchange(-1,'hello',[8],descriptor)==descriptor
    ch.exchange(0,'arithmetic_masks',[2,1],[0,0],span=['arithmetic',0,1])
    proc.kill();proc.communicate(timeout=10);sock.close()
    db=sqlite3.connect(ROOT/'state/mpc/S1-ledger.sqlite')
    used=db.execute('SELECT count(*) FROM consumption WHERE batch=? AND kind=?',(prep['batch'],'arithmetic')).fetchone()[0]
    state=db.execute('SELECT state FROM batches WHERE batch=?',(prep['batch'],)).fetchone()[0];db.close()
    assert used==1 and state=='reserved_burn_on_abort'
    proc,sock,attempt=launch(directory,sid,32,peer=False);proc.communicate(timeout=10);sock.close()
    restart=json.loads((directory/'S1'/('metrics-'+attempt+'.json')).read_text())
    assert restart['error']=='BATCH_ALREADY_RESERVED'
    failures.append(dict(name='killed_after_mask_exchange',consumed_arithmetic=used,durable_state=state,restart_error=restart['error']))
    return failures

def main():
    full,completed=full_tests();small=small_tests();failure=negative_tests(completed)
    unchanged=[]
    for item in json.loads((ROOT/'results/material-manifest.json').read_text()):
        assert hashlib.sha256((ROOT/'参考资料'/item['file']).read_bytes()).hexdigest()==item['sha256'];unchanged.append(item['file'])
    summary=dict(status='PASS_LOCAL_PASSIVE_TRUSTED_OFFLINE_PROTOCOL_TESTS',correctness={'full32':full,'small_exhaustive':small},failure_tests=failure,original_materials_unchanged=unchanged,limits=['same-user local IPC, no cross-machine authentication','no active security, proof/audit not supplied','verifier range checks only; no shared range protocol','dealer must not collude or observe online masks','stage1 hashes remain reference-only'])
    (RESULTS/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'status':summary['status'],'full32_checks':full['checks'],'small_checks':sum(x['checks'] for x in small),'wire_bytes_full32':full['wire_bytes'],'rounds_full32':full['exchange_rounds'],'consumed_full32':full['dealer']['generated'],'negative_tests':len(failure)},indent=2))
if __name__=='__main__':main()
