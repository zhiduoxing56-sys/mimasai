"""Injected application failures with tiny one-shot batches, no GNN training.

Backend completion uses a role-ledger/checkpoint fixture, explicitly NOT a
classification run. Final-export authorization is also tested with synthetic
bound output shares through the real role I/O subprocess.
"""
import argparse,copy,json,secrets,sys,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import application as app,storage,offline,runtime
from src.mpc import ROOT,VERSION,ProtocolError
from src.model import binding
from src.processes import StopUnconfirmed
from src.retention import preview,auto

rows=[];material_samples=[]
def ample(*args):return dict(internal_available_bytes=1<<60,host_available_bytes=1<<60,host_status='TEST')
def expect(code,fn):
    try:fn()
    except ProtocolError as error:assert str(error).startswith(code),(code,str(error));return
    raise AssertionError('expected '+code)
def setup(command='execute'):
    eid=secrets.token_hex(16);sid=secrets.token_hex(16);root,out=app.paths(eid)
    out.mkdir(parents=True);d=root/'requests'/sid
    for r in (0,1):(d/f'S{r}').mkdir(parents=True,mode=0o700);(root/f'S{r}').mkdir(exist_ok=True,mode=0o700)
    plan=[dict(type='mul',count=1)]
    model=binding(secrets.token_hex(16),['toy-node'],1,1,2,7)
    manifest=dict(dimensions=[1,1,1,2],data=dict(feature_columns=[0],label_names=['a','b'],node_order=['toy-node']),allowed_targets=['toy-node'],receiver_id='toy-recipient',checkpoint=dict(directory=str(root/'checkpoint'),attempt='toy-attempt',iteration=1))
    app.save(eid,manifest)
    request=dict(session=sid,directory=str(d),plan=plan,delivery=dict(model=model,targets=['toy-node'],receiver_id='toy-recipient',request_id=sid),route='shared')
    if command=='execute':
        with patch.object(storage,'snapshot',ample):request['offline']=offline.generate(d,sid,32,plan)
        samples=[app.read(d/f'S{role}/preprocessing.json')['materials']['arithmetic'][0] for role in (0,1)]
        material_samples.append(tuple(tuple(values) for values in samples))
    app.write(out/f'request-{sid}.json',request)
    return argparse.Namespace(command=command,experiment=eid,request=sid),d,request

def completed_backend(d,sid,bits,**kwargs):
    attempt,metrics=runtime.launch(d,sid,bits,worker='verification.storage_success_worker',defer_completion=True)
    for metric in metrics:metric['communication']=None
    return attempt,metrics

def fixture_io(operation,role,source,destination,attempt=None):
    source=Path(source);destination=Path(destination)
    if operation=='export':app.write(destination/f'S{role}.json',dict(synthetic_export=True,role=role,request=source.name))
    elif operation=='query_input':app.write(destination/f'S{role}/input.json',dict(synthetic_input=True))
    else:
        plan=app.read(destination/'public-plan.json')['plan']
        for op in plan:app.write(destination/f'S{role}/model-{op["model"]["model_id"]}.json',dict(synthetic_model=True,role=role))

def execution_fault(name):
    args,d,request=setup();sid=request['session'];real_write=app.write
    def io(operation,role,*rest):
        if name=='input_preparation' and operation=='query_input':raise OSError('injected input preparation failure')
        if name=='export_interrupt' and role==1 and operation=='export':raise KeyboardInterrupt('injected delivery interruption')
        if name==f'export_S{role}' and operation=='export':
            if role==0:fixture_io(operation,role,*rest) # First export can fail after durable creation.
            raise OSError('injected export failure')
        fixture_io(operation,role,*rest)
    def save(path,value):
        if Path(path).name==f'request-{sid}.json' and ((name=='report_save' and value.get('attempt')) or (name=='report_commit' and value.get('success')) or name=='report_start'):
            raise OSError('injected report persistence failure')
        real_write(path,value)
    def backend(*values,**kw):
        if name=='interrupt':raise KeyboardInterrupt('injected interruption')
        if name=='stop_unconfirmed':raise StopUnconfirmed('injected stop inspection failure')
        return completed_backend(*values,**kw)
    probe=(lambda *values:dict(internal_available_bytes=0,host_available_bytes=1<<60,host_status='TEST')) if name=='capacity_admission' else ample
    with patch.object(storage,'snapshot',probe),patch.object(app,'role_io',io),patch.object(app,'launch',backend),patch.object(app,'write',save):
        try:app.command(args)
        except (OSError,KeyboardInterrupt,ProtocolError):pass
        else:raise AssertionError('fault did not fail')
    entry=storage.record(sid);events=storage.history(sid)
    assert entry['state']==('stopping' if name=='stop_unconfirmed' else 'cleaned')
    failures=[v for v in events if v.get('status')=='failed']
    assert failures and all(v['reason'] for v in failures)
    assert not any(v['stage']=='completed' for v in events)
    expect('SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE',lambda:storage.reject_burned(entry['batch']))
    expect('SESSION_STATE_REJECTED',lambda:runtime.launch(d,sid,32))
    report=app.read(app.paths(args.experiment)[1]/f'request-{sid}.json')
    assert not report.get('success',False)
    assert storage.public_status(sid)['delivery_state']=='incomplete'
    assert storage.public_status(sid)['failure_reason'] and '/' not in storage.public_status(sid)['failure_reason']
    if name not in ('report_save','report_start'):assert report['delivery_state']=='incomplete'
    shares=list((app.paths(args.experiment)[1]/'receiver'/sid).glob('S*.json'))
    assert len(shares)==(2 if name=='report_commit' else (1 if name in ('export_S0','export_S1','export_interrupt') else 0))
    if name=='stop_unconfirmed':expect('SESSION_NOT_TERMINAL',lambda:preview(sid))
    rows.append(dict(case=name,session=sid,state=entry['state'],failure_stages=[v['stage'] for v in failures],partial_export_files=len(shares),rerun_rejected=True,cleanup_observation=report.get('retention')))

def publication_fault(name):
    args,d,request=setup('publish');real_write=app.write
    def dealer(destination,sid,plan):
        app.write(destination/'public-plan.json',dict(plan=plan,session=sid,bits=32))
        result=offline.generate(destination,sid,32,[dict(type='add',count=1)])
        return result
    def io(operation,role,*rest):
        if name=='publication_input' and operation=='publication_input':raise OSError('injected publication input failure')
        fixture_io(operation,role,*rest)
    def save(path,value):
        if name in ('publication_report','publication_report_after_replace') and Path(path).name=='manifest.json' and value.get('publication'):
            if name=='publication_report_after_replace':real_write(path,value)
            raise OSError('injected publication manifest save failure')
        real_write(path,value)
    real_link=app.os.link
    def link(source,destination):
        if name=='model_install' or Path(destination).parent.name=='S1':raise OSError('injected model install failure')
        return real_link(source,destination)
    with patch.object(storage,'snapshot',ample),patch.object(app,'dealer',dealer),patch.object(app,'role_io',io),patch.object(app,'launch',completed_backend),patch.object(app,'write',save):
        try:
            if name in ('model_install','model_install_S1'):
                with patch.object(app.os,'link',link):app.command(args)
            else:app.command(args)
        except OSError:pass
        else:raise AssertionError('publication fault missing')
    reports=list(app.paths(args.experiment)[1].glob('publication-*.json'));assert len(reports)==1
    publication=app.read(reports[0]);sid=publication['session'];entry=storage.record(sid)
    assert entry['state']=='cleaned' and publication['success'] is False
    assert not storage.committed(sid)
    cached=app.read(app.report_path(args.experiment))
    if name=='publication_report_after_replace':
        assert 'publication' in cached
        cached['he_setup']={};real_write(app.report_path(args.experiment),cached)
        request_args=argparse.Namespace(command='request',experiment=args.experiment,route='he',activation='fss',target=None)
        expect('PUBLICATION_NOT_COMMITTED',lambda:app.command(request_args))
    else:assert 'publication' not in cached
    expect('SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE',lambda:storage.reject_burned(entry['batch']))
    rows.append(dict(case=name,session=sid,state=entry['state'],failure_stage=publication['failure_stage'],rerun_rejected=True))

def success_and_lock():
    args,d,request=setup();sid=request['session'];lock_errors=[]
    def io(operation,role,*rest):
        if operation=='export':
            def contender():
                try:
                    with storage.workflow_lease(sid):raise AssertionError('delivery lock lost')
                except ProtocolError as error:lock_errors.append(str(error))
            t=threading.Thread(target=contender);t.start();t.join()
            expect('SESSION_NOT_TERMINAL',lambda:preview(sid))
        fixture_io(operation,role,*rest)
    with patch.object(storage,'snapshot',ample),patch.object(app,'role_io',io),patch.object(app,'launch',completed_backend):result=app.command(args)
    saved=app.read(app.paths(args.experiment)[1]/f'request-{sid}.json')
    assert result['status']=='TARGET_SHARES_DELIVERED' and saved['success'] and saved['delivery_state']=='complete'
    assert saved['exported_roles']==[0,1] and lock_errors==['SESSION_ACTIVE']*2
    expect('REQUEST_EXECUTION_STATE',lambda:app.command(args))
    rows.append(dict(case='success_fixture',session=sid,state=storage.record(sid)['state'],delivery_lock_verified=True,repeated_execution_rejected=True))

def offline_fault(name):
    args,d,request=setup('offline');sid=request['session'];real_write=app.write
    def save(path,value):
        if name=='offline_report_save' and Path(path).name==f'request-{sid}.json' and value.get('offline'):
            raise OSError('injected offline report save failure')
        real_write(path,value)
    def dealer(destination,session,plan):
        result=offline.generate(destination,session,32,plan)
        result['offline_wall_seconds']=0
        if name=='offline_after_generation':raise KeyboardInterrupt('injected interruption after generation')
        return result
    with patch.object(storage,'snapshot',ample),patch.object(app,'dealer',dealer),patch.object(app,'write',save):
        try:app.command(args)
        except (OSError,KeyboardInterrupt):pass
        else:raise AssertionError('offline fault missing')
    entry=storage.record(sid);assert entry['state']=='cleaned'
    assert storage.public_status(sid)['delivery_state']=='incomplete'
    expect('SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE',lambda:storage.reject_burned(entry['batch']))
    rows.append(dict(case=name,session=sid,state=entry['state'],failure_stage=storage.public_status(sid)['failure_stage'],rerun_rejected=True))

def notification_failure(error_type=StopUnconfirmed):
    args,d,request=setup();sid=request['session']
    # If a role notifier's process group itself cannot be confirmed stopped,
    # the central tombstone still rejects reuse but cleanup must stay blocked.
    with patch('src.processes.run',side_effect=error_type('injected notifier failure')):
        storage.burn(sid,'fixture terminal request',stopped=True)
    assert storage.record(sid)['state']=='stopping' and not storage.stopped(sid)
    expect('SESSION_NOT_TERMINAL',lambda:preview(sid))
    expect('SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE',lambda:storage.reject_burned(storage.record(sid)['batch']))
    rows.append(dict(case='notifier_stop_unconfirmed' if error_type is StopUnconfirmed else 'notifier_receipt_save_failed',session=sid,state='stopping',cleanup_rejected=True,rerun_rejected=True))

def export_authorization():
    args,d,request=setup();sid=request['session'];model=request['delivery']['model'];policy=request['delivery'];attempt='synthetic-output'
    ops=[dict(type='probability',dims=[1,2],fraction=model['probability_fraction_bits']),dict(type='deliver',model=model,targets=policy['targets'],receiver_id=policy['receiver_id'],dims=[1,2],use_previous=True)]
    received=app.paths(args.experiment)[1]/'receiver'/sid;received.mkdir(parents=True,mode=0o700)
    for role in (0,1):
        app.write(d/f'S{role}/input.json',dict(session=sid,delivery=policy,operations=ops))
        app.write(d/f'S{role}/query-policy.json',dict(model=model,allowed_targets=policy['targets'],receiver_id=policy['receiver_id']))
        result=dict(role=role,session=sid,delivery=policy,shares=[[0,0]])
        app.write(d/f'S{role}/output-{attempt}.json',result)
    original=app.read(d/f'S1/output-{attempt}.json');wrong=copy.deepcopy(original);wrong['delivery']['receiver_id']='unauthorized'
    app.write(d/f'S1/output-{attempt}.json',wrong)
    try:app.role_io('export',1,d,received,attempt)
    except Exception as error:assert 'ROLE_IO_RESULT_BINDING' in error.stderr
    else:raise AssertionError('unauthorized output accepted')
    assert not (received/'S1.json').exists()
    app.write(d/f'S1/output-{attempt}.json',original)
    for role in (0,1):app.role_io('export',role,d,received,attempt)
    docs=[app.read(received/f'S{r}.json') for r in (0,1)]
    assert all(v['request_id']==sid and v['receiver_id']==policy['receiver_id'] and len(v['shares'])==2 for v in docs)
    storage.burn(sid,'synthetic export fixture complete',stopped=True);auto(sid)
    rows.append(dict(case='real_export_helper_synthetic_final_shares',session=sid,authorization_binding_rejected=True,final_only_export_verified=True,delivery_repair_supported=False))

def main():
    for case in ('capacity_admission','input_preparation','export_S0','export_S1','report_save','report_start','report_commit','interrupt','export_interrupt','stop_unconfirmed'):execution_fault(case)
    for case in ('publication_input','model_install','model_install_S1','publication_report','publication_report_after_replace'):publication_fault(case)
    for case in ('offline_report_save','offline_after_generation'):offline_fault(case)
    notification_failure()
    notification_failure(OSError)
    success_and_lock();export_authorization()
    batches=[storage.record(row['session'])['batch'] for row in rows]
    assert len(set(batches))==len(batches)
    assert len(set(material_samples))==len(material_samples) and len(material_samples)>=10
    out=ROOT/'results/lifecycle';out.mkdir(parents=True,exist_ok=True)
    result=dict(status='PASS_CHANGED_APPLICATION_LIFECYCLE',evidence_kind='Independent short synthetic fault runs; no classifier/protocol accuracy claim',cases=rows,new_batches_distinct=True,new_actual_arithmetic_materials_distinct=True,material_pairs_checked=len(material_samples),training_executed=False)
    (out/'application-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],cases=len(rows),new_batches_distinct=True)))
if __name__=='__main__':main()
