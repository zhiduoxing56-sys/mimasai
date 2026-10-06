"""Changed checkpoint-stop path only; no training or cryptographic material."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.real_data import save_stopped
from src.mpc import ROOT

def main():
 with tempfile.TemporaryDirectory(dir=ROOT/'build/storage-tests') as name:
  d=Path(name);cp=d/'successful';cp.mkdir();share=cp/'output-ok.json';share.write_text('retained-checkpoint-fixture');before=share.read_bytes();out=d/'report.json';state={}
  save_stopped(state,out,[],2,1,'HOST_SPACE_LOW')
  refused=json.loads(out.read_text());assert refused['status']=='SHARED_TRAINING_REFUSED' and 'checkpoint' not in refused
  secure=[dict(directory=str(cp),attempt='ok')]
  save_stopped(state,out,secure,2,2,'INTERNAL_SPACE_LOW')
  stopped=json.loads(out.read_text());assert stopped['status']=='SHARED_TRAINING_STOPPED' and stopped['secure_steps']==1
  assert stopped['checkpoint']==dict(directory=str(cp),attempt='ok',parameter_count=2,iteration=1)
  assert stopped['storage_stop']['next_iteration']==2 and share.read_bytes()==before
 result=dict(status='PASS_CHANGED_TRAINING_STOP_REPORT',first_step_refusal_without_checkpoint=True,last_successful_checkpoint_preserved=True,atomic_stop_report=True,training_executed=False,materials_generated=False)
 (ROOT/'results/storage/training-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
