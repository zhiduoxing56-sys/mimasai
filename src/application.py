"""Local owner/dealer coordinator. Separate commands; no query-result recovery.
Owner preparation uses public Cora. Servers never import this module. The
independent receiver accepts only exported target shares, not this workspace.
"""
import argparse,copy,json,os,secrets,struct,subprocess,sys,time
from pathlib import Path
from .mpc import ROOT,VERSION,private_write,settings,require
from .reference import Fixed
from .data import cora
from .model import binding
from .ranges import operand,bit_width
from .runtime import launch
from .processes import run as supervised_run
from .lifecycle import Workflow
from .he import native,binary_write,file_hash

flat=lambda rows:[v for row in rows for v in row]

def paths(identifier):
    require(len(identifier)==32 and all(c in '0123456789abcdef' for c in identifier),'EXPERIMENT_ID')
    return ROOT/'build/application'/identifier, ROOT/'results/application'/identifier

def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.pending-'+secrets.token_hex(8));private_write(temporary,value);os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def report_path(identifier):return paths(identifier)[1]/'manifest.json'
def save(identifier,report):write(report_path(identifier),report)
def command(args):
    c=settings()
    if args.command=='prepare':
        from .storage import check
        check(ROOT,128*1024**2)
        started=time.perf_counter();data=cora(args.archive,args.download,node_count=args.nodes,sampling=args.sampling,seed=args.seed);eid=secrets.token_hex(16);root,out=paths(eid);out.mkdir(parents=True)
        for name in ('S0','S1','V'):(root/name).mkdir(parents=True,mode=0o700)
        write(root/'V/data.json',data)
        fx=Fixed(c);p=flat(fx.encode(data['propagation']));x=flat(fx.encode(data['features']));mod=1<<c['ring_bits']
        pairs=[{},{}]
        for name,values in [('p',p),('x',x)]:
            first=[secrets.randbelow(mod) for _ in values];second=[(v-a)%mod for v,a in zip(values,first)]
            for role,shares in enumerate((first,second)):pairs[role][name]=shares
        for role in (0,1):write(root/f'S{role}/input-shares.json',pairs[role])
        targets=args.target or [data['node_order'][data['splits']['test'][0]]]
        require(len(set(targets))==len(targets) and all(t in data['node_order'] for t in targets),'QUERY_TARGETS')
        report=dict(experiment_id=eid,version='cora-local-application-v1',nodes=len(data['node_order']),dimensions=[len(data['node_order']),len(data['feature_columns']),c['model_reference']['hidden_width'],len(data['label_names'])],data={k:v for k,v in data.items() if k not in ('features','propagation','labels','edges')},allowed_targets=targets,receiver_id=args.receiver,owner_preparation_seconds=time.perf_counter()-started,privacy='Public Cora owner-side normalization; not private normalization',authorization='Local controlled policy files, no cryptographic authentication')
        save(eid,report);return dict(experiment_id=eid,command='prepare',manifest=str(report_path(eid)))
    root,out=paths(args.experiment);report=read(out/'manifest.json');data=None
    if args.command in ('reference','train'):
        destination=out/'training';destination.mkdir(exist_ok=True)
        if args.command=='train' and args.checkpoint_report:
            trained=read(args.checkpoint_report);require(trained['status'] in ('SHARED_TRAINING_PASS','SHARED_TRAINING_STOPPED') and trained['secure_steps']>0 and trained['checkpoint']['iteration']==len(trained['secure_training']) and all(m['success'] for m in trained['secure_training'][-1]['servers']) and trained['data']['node_order']==report['data']['node_order'] and trained['dimensions']==report['dimensions'] and all(trained['data'][key]==report['data'][key] for key in ('archive_sha256','feature_columns','label_names','preprocessing')),'ACTUAL_CHECKPOINT_REQUIRED');write(destination/'reference.json',trained)
        else:
            cmd=[sys.executable,'verification/real_data.py','--nodes',str(report['nodes']),'--output-directory',str(destination),'--sampling',report['data'].get('sampling','fixed_bfs'),'--sampling-seed',str(report['data'].get('sampling_seed',c['data_experiment']['representative']['primary_seed']))]
            if args.command=='train':cmd+=['--secure-steps',str(args.steps)]
            if args.resume:cmd+=['--resume']
            with (out/f'{args.command}.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        result=read(destination/'reference.json');report['training_report']=str(destination/'reference.json')
        if result['status'] in ('SHARED_TRAINING_PASS','SHARED_TRAINING_STOPPED') and result.get('secure_steps',0)>0:report['checkpoint']=result['checkpoint'];report['training_steps']=result['secure_steps']
        save(args.experiment,report);return dict(command=args.command,status=result['status'],steps=result.get('secure_steps',0),report=report['training_report'])
    if args.command=='publish':
        from .storage import check
        check(root,128*1024**2)
        require('checkpoint' in report and 'publication' not in report,'PUBLICATION_STATE')
        checkpoint=report['checkpoint'];source=Path(checkpoint['directory']);n,ff,h,classes=report['dimensions'];ft=c['training_reference']['fraction_bits'];f=c['fraction_bits'];layout=dict(feature_order=[f'word-{j}' for j in report['data']['feature_columns']],class_order=report['data']['label_names']);m12=binding(secrets.token_hex(16),report['data']['node_order'],ff,h,classes,ft,**layout);m7=binding(secrets.token_hex(16),report['data']['node_order'],ff,h,classes,f,**layout);count=ff*h+h*classes;sid=secrets.token_hex(16);d=root/'publication'/sid
        plan=[dict(type='publish',count=count,source_fraction=ft,model=m12),dict(type='publish',count=count,source_fraction=ft,model=m7,use_previous=True)]
        publication=dict(directory=str(d),session=sid,models=[m12,m7],source_training_iteration=checkpoint['iteration'],source_training_session=source.name)
        def persist_publication():
            write(out/f'publication-{sid}.json',publication)
            if publication.get('success'):
                report['publication']=publication;save(args.experiment,report)
        with Workflow(sid,publication,persist_publication) as work:
            work.phase('publication_directory')
            for role in (0,1):(d/f'S{role}').mkdir(parents=True,mode=0o700)
            work.phase('offline_generation');publication['offline']=dealer(d,sid,plan)
            from .storage import lease,transition
            with lease(sid):transition(sid,{'ready'},'preparing')
            work.phase('publication_input')
            for role in (0,1):role_io('publication_input',role,source,d,checkpoint['attempt'])
            work.phase('publication_backend');started=time.perf_counter()
            attempt,metrics=launch(d,sid,c['ring_bits'],timeout=240,defer_completion=True)
            require(all(m['success'] for m in metrics),'PUBLICATION_FAILED')
            publication.update(attempt=attempt,online=statistics(metrics,time.perf_counter()-started))
            for role in (0,1):
                work.phase(f'model_install_S{role}')
                os.link(d/f'S{role}/model-{m7["model_id"]}.json',root/f'S{role}/model-{m7["model_id"]}.json')
                write(root/f'S{role}/query-policy.json',dict(model=m7,allowed_targets=report['allowed_targets'],receiver_id=report['receiver_id']))
            publication['success']=True
            work.complete()
            from .retention import auto
            publication['retention']=auto(sid);persist_publication();save(args.experiment,report)
        return dict(command='publish',model_id=m7['model_id'],source_iteration=checkpoint['iteration'])
    if args.command=='provision':
        from .storage import check,committed
        check(root,512*1024**2)
        require('publication' in report and 'he_setup' not in report,'PROVISION_STATE');require(committed(report['publication']['session']),'PUBLICATION_NOT_COMMITTED');data=read(root/'V/data.json');model=report['publication']['models'][-1];n,ff,h,classes=report['dimensions'];fx=Fixed(c);p=fx.encode(data['propagation']);require(all(0<=v<=fx.scale for row in p for v in row),'OWNER_PROPAGATION_DOMAIN');setup=root/'he-assets'
        for name in ('S0','S1','V'):(setup/name).mkdir(parents=True,mode=0o700)
        binary_write(setup/'V/propagation.bin',struct.pack('<'+'I'*(n*n),*flat(p)));started=time.perf_counter();native_stats=native(['setup',setup,c['he_execution_degree'],c['ring_bits'],*c['he_coefficient_bits'],n,h]);native_stats['wall_seconds']=time.perf_counter()-started
        qs=native(['metadata',setup/'S0'])['data_moduli'];pub=dict(package_id=secrets.token_hex(16),key_ids=[file_hash(setup/f'S{r}/eval.pk')[:32] for r in (0,1)],parameters_id=file_hash(setup/'S0/parameters.seal'),degree=c['he_execution_degree'],ring_bits=c['ring_bits'],shape=[n,h],node_order=model['node_order'],column_order=[f'hidden-{j}' for j in range(h)],input_scale=1<<c['fraction_bits'],output_scale=1<<(2*c['fraction_bits']),data_moduli=qs)
        for role in (0,1):
            own=setup/f'S{role}';files=['eval.pk','eval.gk','peer.sk','parameters.seal']+[f'rows/{i}.ct' for i in range(n)];integrity={name:file_hash(own/name) for name in files}
            for layer,width in ((0,h),(1,classes)):
                target=root/f'S{role}/he-layer{layer}';target.mkdir(mode=0o700);(target/'rows').mkdir(mode=0o700)
                for name in files:os.link(own/name,target/name)
                current=copy.deepcopy(pub);current.update(shape=[n,width],column_order=pub['column_order'] if layer==0 else model['class_order']);write(target/'he.json',dict(role=role,public=current,local_integrity=integrity))
        report['he_setup']=dict(directory=str(setup),public=pub,cost=native_stats);save(args.experiment,report);return dict(command='provision',status='HE_ASSETS_READY',key_ids=pub['key_ids'])
    if args.command=='request':
        require('publication' in report and 'he_setup' in report,'REQUEST_MODEL_NOT_READY');from .storage import check,estimate,committed
        require(committed(report['publication']['session']),'PUBLICATION_NOT_COMMITTED')
        from .mpc import costs
        targets=args.target or report['allowed_targets'];preview_plan=inference_plan(report,args.route,args.activation,targets)
        check(root,estimate(preview_plan,costs(preview_plan,c['ring_bits']))['total_bytes'])
        sid=secrets.token_hex(16);d=root/'requests'/sid;model=report['publication']['models'][-1];targets=args.target or report['allowed_targets'];require(targets and len(set(targets))==len(targets) and all(t in report['allowed_targets'] for t in targets),'QUERY_UNAUTHORIZED_TARGET');plan=inference_plan(report,args.route,args.activation,targets);delivery=dict(model=model,targets=targets,receiver_id=report['receiver_id'],request_id=sid)
        for role in (0,1):
            own=d/f'S{role}';own.mkdir(parents=True,mode=0o700)
            for name in (f'model-{model["model_id"]}.json','query-policy.json'):os.link(root/f'S{role}'/name,own/name)
            if args.route=='he':
                for layer in (0,1):
                    origin=root/f'S{role}/he-layer{layer}';target=own/origin.name;target.mkdir(mode=0o700);(target/'rows').mkdir(mode=0o700)
                    for file in origin.rglob('*'):
                        if file.is_file():os.link(file,target/file.relative_to(origin))
        if args.route=='he':os.link(d/'S0/he-layer0/parameters.seal',d/'parameters.seal')
        write(d/'public-plan.json',dict(session=sid,bits=c['ring_bits'],plan=plan));request=dict(session=sid,directory=str(d),plan=plan,delivery=delivery,route=args.route,activation=args.activation);write(out/f'request-{sid}.json',request);return dict(command='request',request=sid,route=args.route,activation=args.activation)
    require(len(args.request)==32 and all(v in '0123456789abcdef' for v in args.request),'REQUEST_ID');request=read(out/f'request-{args.request}.json');d=Path(request['directory']);sid=request['session']
    if args.command=='status':
        from .storage import public_status
        return public_status(sid)
    if args.command=='offline':
        require(not request.get('offline_started') and 'offline' not in request and not any((d/f'S{r}/preprocessing.json').exists() for r in (0,1)),'REQUEST_MATERIAL_EXISTS')
        with Workflow(sid,request,lambda:write(out/f'request-{sid}.json',request)) as work:
            work.phase('offline_report_start');request['offline_started']=True;write(out/f'request-{sid}.json',request)
            work.phase('offline_generation');request['offline']=dealer(d,sid,request['plan'])
            work.phase('offline_report_save');write(out/f'request-{sid}.json',request)
        return dict(command='offline',request=sid,generated=request['offline']['generated'],disk_budget=request['offline']['disk_budget'],offline_wall_seconds=request['offline']['offline_wall_seconds'])
    if args.command=='execute':
        require('offline' in request and not request.get('execution_started') and 'attempt' not in request,'REQUEST_EXECUTION_STATE')
        with Workflow(sid,request,lambda:write(out/f'request-{sid}.json',request),claim=True) as work:
            from .storage import Guard,record
            work.phase('input_capacity_admission');Guard(d,sid,record(sid)['budget']).check(force=True)
            work.phase('execution_report_start');request.update(execution_started=True,success=False,delivery_state='not_started',exported_roles=[])
            write(out/f'request-{sid}.json',request)
            work.phase('input_preparation')
            write(d/'job-template.json',dict(session=sid,bits=c['ring_bits'],operations=request['plan'],delivery=request['delivery'],route=request['route']))
            for role in (0,1):role_io('query_input',role,root,d)
            work.phase('backend');started=time.perf_counter()
            attempt,metrics=launch(d,sid,c['ring_bits'],timeout=300,defer_completion=True)
            request.update(attempt=attempt,online=statistics(metrics,time.perf_counter()-started),backend_success=all(m['success'] for m in metrics))
            require(request['backend_success'],'REQUEST_FAILED')
            work.phase('backend_report_save');write(out/f'request-{sid}.json',request)
            received=out/'receiver'/sid;received.mkdir(parents=True,mode=0o700)
            for role in (0,1):
                work.phase(f'export_S{role}');role_io('export',role,d,received,attempt)
                request['exported_roles'].append(role)
                from .storage import event
                event(sid,f'export_S{role}',status='persisted',receiver_id=request['delivery']['receiver_id'],request_id=sid)
                request['delivery_state']='partial'
            # Only both durable final exports can be a complete delivery.
            request.update(success=True,delivery_state='complete');work.complete()
            from .retention import auto
            work.phase('retention');request['retention']=auto(sid)
            work.phase('retention_report_save');write(out/f'request-{sid}.json',request)
        return dict(command='execute',request=sid,status='TARGET_SHARES_DELIVERED',receiver_directory=str(received),retention=request['retention'],online={k:v for k,v in request['online'].items() if k!='servers'})
    raise ValueError('unknown application command')

def role_io(operation,role,source,destination,attempt=None):
    cmd=[sys.executable,'-m','src.role_io',operation,str(role),str(source),str(destination)]
    if attempt:cmd+=['--attempt',attempt]
    supervised_run(cmd,cwd=ROOT)

def model_classes(request):return request['delivery']['model']['dimensions'][2]
def statistics(metrics,wall):
    return dict(wall_seconds=wall,wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics if m['communication']),rounds=metrics[0]['communication']['exchange_rounds'] if metrics[0]['communication'] else 0,servers=[{k:v for k,v in m.items() if k!='message_trace'} for m in metrics],counting='Both-direction sent bytes incl headers, paired exchange rounds; no nested double counting; per-process cumulative RSS highwater')
def dealer(directory,sid,plan):
    started=time.perf_counter();write(directory/'public-plan.json',dict(session=sid,bits=settings()['ring_bits'],plan=plan));p=supervised_run([sys.executable,'-m','src.offline',str(directory),str(directory/'public-plan.json')],cwd=ROOT);result=json.loads(p.stdout);result['offline_wall_seconds']=time.perf_counter()-started;return result

def inference_plan(report,route,activation,targets):
    c=settings();model=report['publication']['models'][-1];n,ff,h,classes=report['dimensions'];f=c['fraction_bits'];pf=c['probability_fraction_bits'];k=lambda key:operand(key,f)
    plan=[dict(type='matmul',model=model,model_layer=0,input_feature_order=model['feature_order'],dims=[n,ff,h],fraction=f,bounds=[k('feature'),k('weight')],range_strategy='row_l1')]
    for layer,width in ((0,h),(1,classes)):
        common=dict(count=n*width,fraction=f,k=bit_width(k('state')),activation=activation if layer==0 else 'none',use_previous=True,range_strategy='row_l1')
        if route=='he':
            public=copy.deepcopy(report['he_setup']['public']);public.update(shape=[n,width],column_order=public['column_order'] if layer==0 else model['class_order']);op=dict(common,type='he_aggregate',model=model,model_layer=layer,he=public,he_slot=f'he-layer{layer}',conversion='private_decryption',input_bound=k('state'))
        else:op=dict(common,type='shared_aggregate',dims=[n,n,width],bounds=[k('propagation'),k('state')])
        plan.append(op)
        if layer==0:plan.append(dict(type='matmul',model=model,model_layer=1,dims=[n,h,classes],fraction=f,bounds=[k('state'),k('weight')],use_previous=True,previous_slice=[(2 if route=='he' else 1)*n*h,n*h],range_strategy='row_l1'))
    plan.extend([dict(type='precision_up',count=n*classes,source_fraction=f,fraction=pf,use_previous=True,previous_slice=[n*classes if route=='he' else 0,n*classes]),dict(type='probability',count=n*classes,dims=[n,classes],fraction=pf,use_previous=True),dict(type='deliver',model=model,targets=targets,receiver_id=report['receiver_id'],dims=[n,classes],use_previous=True)])
    return plan

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('prepare');a.add_argument('--nodes',type=int,choices=(16,32,64),default=settings()['data_experiment']['nodes']);a.add_argument('--download',action='store_true');a.add_argument('--archive');a.add_argument('--sampling',choices=('fixed_bfs','uniform','multi_start','stratified_frontier'),default='fixed_bfs');a.add_argument('--seed',type=int);a.add_argument('--target',action='append');a.add_argument('--receiver',default='local-authorized-recipient')
    for name in ('reference','train','publish','provision','request','offline','execute','status'):
        a=s.add_parser(name);a.add_argument('--experiment',required=True)
        if name in ('reference','train'):a.add_argument('--resume',action='store_true')
        if name=='train':a.add_argument('--steps',type=int,default=settings()['data_experiment']['secure_iteration_budget']);a.add_argument('--checkpoint-report')
        if name=='request':a.add_argument('--route',choices=('shared','he'),default='he');a.add_argument('--activation',choices=('boolean','fss'),default='fss');a.add_argument('--target',action='append')
        if name in ('offline','execute','status'):a.add_argument('--request',required=True)
    print(json.dumps(command(p.parse_args()),ensure_ascii=False))
if __name__=='__main__':main()
