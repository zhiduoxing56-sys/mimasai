"""One complete real-data experiment, using independent owner/dealer/receiver commands."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def call(module,*args):
    p=subprocess.run([sys.executable,'-m',module,*map(str,args)],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--nodes',type=int,choices=(16,32,64));p.add_argument('--steps',type=int);p.add_argument('--checkpoint-report');p.add_argument('--validate',action='store_true');p.add_argument('--faults',action='store_true');a=p.parse_args();started=time.perf_counter();prepare=['prepare','--download']
    if a.nodes is not None:prepare+=['--nodes',a.nodes]
    public=call('src.application',*prepare);eid=public['experiment_id'];print(json.dumps(public),flush=True)
    train=['train','--experiment',eid]
    if a.checkpoint_report:train+=['--checkpoint-report',a.checkpoint_report]
    elif a.steps is not None:train+=['--steps',a.steps]
    for args in (train,['publish','--experiment',eid],['provision','--experiment',eid]):print(json.dumps(call('src.application',*args)),flush=True)
    requests=[]
    # Same persistent model, fresh masked request for every call. Repeat HE/FSS
    # before running matching MPC and Boolean variants for comparison.
    for route,activation in [('he','fss'),('he','fss'),('shared','fss'),('he','boolean'),('shared','boolean')]:
        req=call('src.application','request','--experiment',eid,'--route',route,'--activation',activation)['request'];call('src.application','offline','--experiment',eid,'--request',req);result=call('src.application','execute','--experiment',eid,'--request',req);received=call('src.receiver',result['receiver_directory']);requests.append(req);print(json.dumps(dict(request=req,route=route,activation=activation,result=received,online_bytes=result['online']['wire_bytes'],rounds=result['online']['rounds'])),flush=True)
    if a.validate:
        cmd=[sys.executable,'verification/application.py','--experiment',eid,'--diagnostic']
        if a.faults:cmd+=['--faults']
        out=ROOT/'results/application'/eid
        with (out/'validation.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    report=dict(status='PASS_REAL_TRAIN_PUBLISH_TARGET_QUERIES',experiment_id=eid,requests=requests,wall_seconds=time.perf_counter()-started,independent_verifier_run=a.validate)
    (ROOT/'results/application'/eid/'pipeline.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
