"""Reuse a published model; fresh material per query; final-only recipient."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT='a49152b33097752eaf81a7cba6d910a3'

def call(module,*args):
 p=subprocess.run([sys.executable,'-m',module,*map(str,args)],cwd=ROOT,capture_output=True,text=True)
 if p.returncode:
  raise RuntimeError(f'{module} failed: '+p.stderr[-2000:])
 return json.loads(p.stdout)

def emit(stage,**fields):print(json.dumps(dict(stage=stage,**fields),ensure_ascii=False),flush=True)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',default=DEFAULT);p.add_argument('--target',action='append');p.add_argument('--receiver',default='local-authorized-recipient');a=p.parse_args()
 if len(a.experiment)!=32 or any(c not in '0123456789abcdef' for c in a.experiment):p.error('invalid experiment')
 manifest=json.loads((ROOT/'results/application'/a.experiment/'manifest.json').read_text());model=manifest['publication']['models'][-1];targets=a.target or manifest['allowed_targets']
 if a.receiver!=manifest['receiver_id']:p.error('receiver is not authorized by owner policy')
 if not targets or len(set(targets))!=len(targets) or any(t not in manifest['allowed_targets'] for t in targets):p.error('target is not authorized by owner policy')
 emit('model',experiment=a.experiment,model_id=model['model_id'],source_training_iteration=manifest['publication']['source_training_iteration'],source_training_session=manifest['publication']['source_training_session'],dimensions=manifest['dimensions'],sampling=manifest['data'].get('sampling'),sampling_seed=manifest['data'].get('sampling_seed'),targets=targets,receiver=a.receiver,route='real_SEAL_private_decryption_FSS',scope='Trusted local CLI roles; no OS role isolation or web process')
 started=time.perf_counter();request_args=['request','--experiment',a.experiment,'--route','he','--activation','fss']
 for target in targets:request_args+=['--target',target]
 sid=call('src.application',*request_args)['request'];emit('request',request=sid)
 emit('offline_generating',request=sid)
 offline=call('src.application','offline','--experiment',a.experiment,'--request',sid);emit('offline_ready',**offline)
 emit('online_running',request=sid)
 result=call('src.application','execute','--experiment',a.experiment,'--request',sid);emit('delivered',request=sid,online=result['online'],retention=result['retention'])
 received=call('src.receiver',result['receiver_directory'],'--receiver',a.receiver)
 request=json.loads((ROOT/'results/application'/a.experiment/f'request-{sid}.json').read_text());report=dict(request=sid,result=received,model_id=model['model_id'],source_iteration=manifest['publication']['source_training_iteration'],offline=request['offline'],online=result['online'],retention=result['retention'],wall_seconds=time.perf_counter()-started,full_state_recovered=False)
 (ROOT/'results/application'/a.experiment/f'demo-{sid}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');emit('result',**report)
if __name__=='__main__':main()
