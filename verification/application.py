"""Independent verifier: published model oracle, final query and fault evidence.
This executable may read both shares; src.mpc_worker and src.receiver cannot.
"""
import argparse,copy,json,secrets,subprocess,sys,time
from collections import Counter
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.application import paths,read
from src.reference import Fixed,config,precise_softmax
from src.numerical import probability_reference
from src.runtime import launch
from verification.trained_he_chain import run
from verification.real_chain import owner_bundle
from src.query import validate_delivery
from src.mpc import ProtocolError
from src.ranges import operand,bit_width

flat=lambda rows:[v for row in rows for v in row]

def published_reference(eid):
    root,out=paths(eid);report=read(out/'manifest.json');model=report['publication']['models'][-1];source=Path(report['publication']['directory']);own=[read(source/f'S{r}/model-{model["model_id"]}.json')['shares'] for r in (0,1)];w=[(a+b)%(1<<32) for a,b in zip(*own)];ff,h,classes=model['dimensions'];count=ff*h+h*classes;checkpoint=report['checkpoint'];original=Path(checkpoint['directory']);old=[read(original/f'S{r}/output-{checkpoint["attempt"]}.json')['shares'][0][-count:] for r in (0,1)];source_w=[(a+b)%(1<<32) for a,b in zip(*old)];ft=config()['training_reference']['fraction_bits'];f=model['fraction_bits'];expected=[((v if v<1<<31 else v-(1<<32))//(1<<(ft-f)))%(1<<32) for v in source_w];assert w==expected;model12=report['publication']['models'][0];first=[read(source/f'S{r}/model-{model12["model_id"]}.json')['shares'] for r in (0,1)];assert [(a+b)%(1<<32) for a,b in zip(*first)]==source_w;assert all(read(source/f'S{r}/input.json')['operations'][0]['x']==old[r] for r in (0,1));weights=[ [w[i*h:(i+1)*h] for i in range(ff)], [w[ff*h+i*classes:ff*h+(i+1)*classes] for i in range(h)]];data=read(root/'V/data.json');c=config();fx=Fixed(c);trace=fx.forward(fx.encode(data['propagation']),fx.encode(data['features']),weights,'transform_then_aggregate');scaled=[[fx.signed(v)*(1<<(c['probability_fraction_bits']-c['fraction_bits'])) for v in row] for row in trace['logits']];prob,_=probability_reference(scaled,c['probability_fraction_bits']);high=precise_softmax(fx.decode(trace['logits']));error=max(abs(a/(1<<c['probability_fraction_bits'])-float(b)) for row,rr in zip(prob,high) for a,b in zip(row,rr));pub=dict(report['publication'],input_share_directory=str(root),reference=trace,activation_bits=bit_width(operand('state',c['fraction_bits'])),probability_error=error,classification_equal=all(max(range(classes),key=lambda j:row[j])==max(range(classes),key=lambda j:Decimal(high[i][j])) for i,row in enumerate(prob)))
    return report,data,pub,prob

def verify_queries(eid,prob,faults=False):
    root,out=paths(eid);manifest=read(out/'manifest.json');summaries=[]
    for path in sorted(out.glob('request-*.json')):
        request=read(path)
        if not request.get('success'):continue
        sid=request['session'];d=Path(request['directory']);received=out/'receiver'/sid;result=read(received/'result.json');classes=len(manifest['data']['label_names']);expected=[prob[manifest['data']['node_order'].index(t)] for t in request['delivery']['targets']];assert [r['probability_units'] for r in result['results']]==expected
        assert result['model_id']==manifest['publication']['models'][-1]['model_id']
        for role in (0,1):
            output=read(d/f'S{role}/output-{request["attempt"]}.json');assert len(output['shares'])==1 and len(output['shares'][0])==classes*len(expected);assert len(read(received/f'S{role}.json')['shares'])==classes*len(expected)
            assert all(p.startswith(f'S{role}/') for p in request['online']['servers'][role]['loaded_private_files'])
        _,restart=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
        policy_faults=[]
        job=read(d/'S0/input.json');authorization=read(d/'S0/query-policy.json')
        for name,mutate in [('unauthorized_target',lambda j:j['delivery'].update(targets=[next(t for t in manifest['data']['node_order'] if t not in manifest['allowed_targets'])])),('receiver',lambda j:j['delivery'].update(receiver_id='someone-else')),('final_type',lambda j:j['operations'][-1].update(type='add'))]:
            bad=copy.deepcopy(job);mutate(bad)
            try:validate_delivery(bad,authorization)
            except ProtocolError as e:policy_faults.append(dict(name=name,error=e.code))
            else:raise AssertionError(name)
        summaries.append(dict(session=sid,model_id=result['model_id'],route=request['route'],activation=request['activation'],offline=request['offline'],online=request['online'],result=result,restart_errors=[m['error'] for m in restart],policy_rejections=policy_faults,export_bytes=sum((received/f'S{r}.json').stat().st_size for r in (0,1))))
    assert len(summaries)>=2 and len({s['session'] for s in summaries})==len(summaries) and len({s['offline']['batch'] for s in summaries})==len(summaries)
    if faults:
        # Actual server rejection BEFORE work, fresh reserved materials, no outputs.
        # Follow-up launches test whole-batch burn; never alter old ledgers.
        for fault in ('target','receiver','model','scale','columns','parameters','exhaustion','disconnect'):
            p=subprocess.run([sys.executable,'-m','src.application','request','--experiment',eid,'--route','he'],cwd=paths(eid)[0].parents[2],capture_output=True,text=True,check=True);sid=json.loads(p.stdout)['request'];subprocess.run([sys.executable,'-m','src.application','offline','--experiment',eid,'--request',sid],cwd=paths(eid)[0].parents[2],capture_output=True,text=True,check=True);request=read(out/f'request-{sid}.json');d=Path(request['directory'])
            # Use execute to provision own inputs, then mutate before launch by
            # a subprocess monkeypatch only in this verifier process.
            code='''import json,sys\nfrom src import application as a\nfrom src.runtime import launch as original\nfrom src.mpc import ProtocolError
from src.ranges import operand,bit_width\nfault=sys.argv[1]\ndef intercept(d,sid,bits,**kw):\n for role in (0,1):\n  path=d/f'S{role}/input.json';job=json.loads(path.read_text())\n  if fault=='target':job['delivery']['targets']=[next(t for t in job['delivery']['model']['node_order'] if t not in job['delivery']['targets'])];job['operations'][-1]['targets']=job['delivery']['targets']\n  if fault=='receiver':job['delivery']['receiver_id']='unauthorized';job['operations'][-1]['receiver_id']='unauthorized'\n  if fault=='model':job['operations'][0]['model']['model_id']='0'*32\n  if fault=='scale':job['operations'][1]['fraction']+=1\n  if fault=='columns':job['operations'][0]['input_feature_order']=list(reversed(job['operations'][0]['input_feature_order']))\n  if fault=='parameters':job['operations'][1]['he']['degree']*=2\n  path.write_text(json.dumps(job))\n  if fault=='exhaustion':\n   path=d/f'S{role}/preprocessing.json';doc=json.loads(path.read_text());doc['materials']['arithmetic']=[];path.write_text(json.dumps(doc))\n if fault=='disconnect':kw['worker']='verification.he_private_fault_worker'\n return original(d,sid,bits,**kw)\na.launch=intercept\nsys.argv=['application','execute','--experiment',sys.argv[2],'--request',sys.argv[3]]\ntry:a.main()\nexcept ProtocolError:pass\n'''
            subprocess.run([sys.executable,'-c',code,fault,eid,sid],cwd=paths(eid)[0].parents[2],capture_output=True,text=True,check=True);failed=read(out/f'request-{sid}.json');assert not failed['success'];assert not any((d/f'S{r}/output-{failed["attempt"]}.json').exists() for r in (0,1));_,again=launch(d,sid,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in again);summaries.append(dict(fault=fault,session=sid,status='PASS_NO_OUTPUT_AND_BURN',errors=[m['error'] for m in failed['online']['servers']],restart_errors=[m['error'] for m in again]))
    return summaries

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',required=True);p.add_argument('--diagnostic',action='store_true');p.add_argument('--faults',action='store_true');a=p.parse_args();report,data,pub,prob=published_reference(a.experiment);out=paths(a.experiment)[1];runs=[]
    if a.diagnostic:
        for activation in ('boolean','fss'):
            for route in ('shared','he'):
                r=run(pub,route,activation,bundle_factory=lambda:owner_bundle(data),output_directory=out/'validation');runs.append(r)
        assert all(r['restored_verifier_traces']==runs[0]['restored_verifier_traces'] for r in runs)
    queries=verify_queries(a.experiment,prob,a.faults)
    training=read(report['training_report']);steps=training['secure_training'];material_totals=Counter()
    for step in steps:material_totals.update(step['dealer']['generated'])
    accuracy=lambda ids:sum(max(range(len(prob[i])),key=lambda j:prob[i][j])==data['labels'][i] for i in ids)/len(ids)
    majority=Counter(data['labels'][i] for i in data['splits']['train']).most_common(1)[0][0]
    from src.metrics import evaluate
    from src.application import write as private_write
    full_metrics=evaluate(data,[[v/(1<<config()['probability_fraction_bits']) for v in row] for row in prob]);private_write(paths(a.experiment)[0]/'V/evaluation.json',full_metrics)
    aggregate_metrics={name:{k:v for k,v in metric.items() if k!='nodes'} for name,metric in full_metrics.items()}
    effect=dict(published_model_metrics=aggregate_metrics,published_model_accuracy={name:accuracy(ids) for name,ids in data['splits'].items()},majority_test_accuracy=sum(data['labels'][i]==majority for i in data['splits']['test'])/len(data['splits']['test']),class_distribution={name:dict(Counter(data['labels'][i] for i in ids)) for name,ids in data['splits'].items()},checkpoint_curves=[training['curves'][i] for i in sorted({0,min(15,len(steps)-1),min(31,len(steps)-1),min(63,len(steps)-1),len(steps)-1})],reference_test_iteration=training['test_assessed_at_iteration'],reference_float_test_accuracy=training['float_test_accuracy'],reference_fixed_test_accuracy=training['fixed_test_accuracy'],note='Public Cora induced graph, seven canonical classes; test used for final reporting, not hyperparameter selection; checkpoints use training/validation only; approximate standard p-y gradient')
    costs=dict(owner_preparation_seconds=report['owner_preparation_seconds'],training_online_bytes=sum(s['wire_bytes'] for s in steps),training_rounds=sum(s['rounds'] for s in steps),training_launch_seconds=sum(s['seconds'] for s in steps),training_offline_seconds=sum(s['dealer']['offline_wall_seconds'] for s in steps),training_materials=dict(material_totals),training_role_peak_rss_kib=[max(s['servers'][r]['peak_rss_kib'] for s in steps) for r in (0,1)],training_dealer_peak_rss_kib=max(s['dealer']['peak_rss_kib'] for s in steps),publication_online=report['publication']['online'],publication_offline=report['publication']['offline'],he_setup=report['he_setup']['cost'],counting='Paired exchange rounds, both-direction sent bytes including headers; operation/components subdivide totals, not extra costs; setup/files/recipient separate; cumulative RSS per process')
    result=dict(status='PASS_ACTUAL_TRAINED_MODEL_TARGET_ONLY_QUERIES',experiment_id=a.experiment,training_steps=report['training_steps'],checkpoint=report['checkpoint'],checkpoint_to_m12_to_m7_verified=True,source_parameter_count=report['checkpoint']['parameter_count'],model_id=pub['models'][-1]['model_id'],dimensions=report['dimensions'],queries=queries,diagnostic_same_model_all_traces_bitwise=bool(runs),diagnostic_runs=[{k:v for k,v in r.items() if k not in ('servers','restored_verifier_traces')} for r in runs],probability_max_error=pub['probability_error'],classification_equal_high_precision=pub['classification_equal'],effects=effect,costs=costs,query_privacy='Public IDs and local policy; target probabilities only; not hidden target/authenticated deployment')
    (out/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('status','experiment_id','training_steps','dimensions','diagnostic_same_model_all_traces_bitwise','probability_max_error')},indent=2))
if __name__=='__main__':main()
