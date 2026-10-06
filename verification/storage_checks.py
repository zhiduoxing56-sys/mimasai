"""Only changed guards/lifecycle/retention: no historical primitive rerun."""
import json,os,secrets,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import storage,offline,runtime
from src.mpc import Materials,ProtocolError,private_write,VERSION
from src.retention import preview,apply,auto
ROOT=storage.ROOT;OUT=ROOT/'results/lifecycle';OUT.mkdir(parents=True,exist_ok=True)

checks=[]
def expect(code,fn):
 try:fn()
 except ProtocolError as e:
  assert str(e).startswith(code),(code,str(e));checks.append(code);return
 raise AssertionError('expected '+code)
def directory():
 sid=secrets.token_hex(16);d=ROOT/'build/storage-tests'/sid
 for r in (0,1):(d/f'S{r}').mkdir(parents=True,mode=0o700)
 return d,sid
def ample(*args):return dict(internal_available_bytes=1<<60,host_available_bytes=1<<60,host_status='TEST')
def low_internal(*args):return dict(internal_available_bytes=0,host_available_bytes=1<<60,host_status='TEST')
def low_host(*args):return dict(internal_available_bytes=1<<60,host_available_bytes=0,host_status='TEST')
def unknown(*args):return dict(internal_available_bytes=1<<60,host_available_bytes=None,host_status='UNKNOWN')

def main():
 # Budget refusal happens before any material-identifiers/preprocessing writes.
 for probe,code in [(low_internal,'INTERNAL_SPACE_LOW'),(low_host,'HOST_SPACE_LOW'),(unknown,'HOST_SPACE_UNKNOWN')]:
  d,sid=directory()
  with patch.object(storage,'snapshot',probe):expect(code,lambda:offline.generate(d,sid,32,[dict(type='add',count=1)]))
  assert not (d/'material-identifiers.json').exists() and not storage.record(sid)
 # Mid-generation capacity fault permanently burns a created session/batch.
 d,sid=directory();calls=[0]
 def falling(*args):
  calls[0]+=1
  return ample() if calls[0]<=2 else low_host()
 cfg=storage.policy();cfg['monitor_seconds']=0
 with patch.object(storage,'snapshot',falling),patch.object(storage,'policy',lambda:cfg):
  expect('HOST_SPACE_LOW',lambda:offline.generate(d,sid,32,[dict(type='mul',count=8192)]))
 assert storage.record(sid)['state']=='aborted';auto(sid)
 # A prior successful checkpoint is untouched during online safe stop.
 d,sid=directory();checkpoint=d/'S0/output-successful-checkpoint.json';checkpoint.write_text('keep')
 with patch.object(storage,'snapshot',ample):offline.generate(d,sid,32,[dict(type='add',count=1)])
 expect('SESSION_NOT_TERMINAL',lambda:preview(sid))
 with storage.lease(sid):expect('SESSION_ACTIVE',lambda:preview(sid))
 trace=d/'S0/he-layer0/trace';trace.mkdir(parents=True);(trace/'multiply.ct').write_bytes(b'work')
 saved=(d/'S0/preprocessing.json').read_bytes();batch=json.loads(saved)['batch']
 def online_falling(*args):
  return low_internal() if all((d/f'S{r}/reserved-marker.json').exists() for r in (0,1)) else ample()
 with patch.object(storage,'snapshot',online_falling):expect('INTERNAL_SPACE_LOW',lambda:runtime.launch(d,sid,32,worker='verification.storage_worker'))
 assert storage.record(sid)['state']=='aborted' and checkpoint.read_text()=='keep'
 for r in (0,1):
  child=json.loads((d/f'S{r}/reserved-marker.json').read_text())['pid'];path=Path(f'/proc/{child}/stat')
  assert not path.exists() or path.read_text().split()[2]=='Z','grandchild survived abort'
 doc=preview(sid);assert any(f['path']=='S0/preprocessing.json' for f in doc['files'])
 result=apply(doc);assert storage.record(sid)['state']=='cleaned'
 assert checkpoint.read_text()=='keep' and (d/'material-identifiers.json').exists()
 assert not (trace/'multiply.ct').exists()
 assert json.loads(storage.record(sid)['detail'])['termination_state']=='aborted'
 # Restore an old bundle to a different directory; central tombstone refuses.
 restored=ROOT/'build/storage-tests/restored'/sid;restored.mkdir(parents=True)
 old=restored/'preprocessing.json';old.write_bytes(saved)
 expect('SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE',lambda:Materials(old,0,sid,32))
 expect('SESSION_STATE_REJECTED',lambda:runtime.launch(d,sid,32))
 # Backend exit alone does not make application delivery/publish terminal.
 d,sid=directory()
 with patch.object(storage,'snapshot',ample):
  offline.generate(d,sid,32,[dict(type='add',count=1)])
  secret=d/'not-for-child.json';secret.write_text('synthetic inheritable descriptor fixture')
  secret_fd=os.open(secret,os.O_RDONLY);os.set_inheritable(secret_fd,True)
  try:attempt,metrics=runtime.launch(d,sid,32,worker='verification.storage_success_worker',defer_completion=True)
  finally:os.close(secret_fd)
 for role in (0,1):
  fds=json.loads((d/f'S{role}/startup-fds.json').read_text())
  assert fds['0']=='/dev/null' and str(secret) not in fds.values()
  assert all(name in ('0','1','2') or value.startswith('socket:') for name,value in fds.items()),fds
 checks.append('INHERITABLE_SECRET_FD_CLOSED_IN_WORKERS')
 assert all(m['success'] for m in metrics) and storage.record(sid)['state']=='running'
 expect('SESSION_NOT_TERMINAL',lambda:preview(sid))
 storage.transition(sid,{'running'},'completed','authorized exports persisted fixture');auto(sid)
 assert (d/f'S0/output-{attempt}.json').exists()
 checks.append('DELIVERY_PENDING_CLEANUP_REJECTED')
 # One-sided fault helpers also retain the lease and monitor capacity.
 d,sid=directory()
 with patch.object(storage,'snapshot',ample):offline.generate(d,sid,32,[dict(type='add',count=1)])
 def one_falling(*args):return low_host() if (d/'S1/reserved-marker.json').exists() else ample()
 with patch.object(storage,'snapshot',one_falling):
  proc,sock,attempt=runtime.launch(d,sid,32,peer=False,worker='verification.storage_worker')
  expect('SESSION_ACTIVE',lambda:preview(sid))
  proc.storage_monitor.join(timeout=10);proc.communicate(timeout=1);sock.close()
  deadline=time.monotonic()+5
  while storage.record(sid)['state']=='running' and time.monotonic()<deadline:time.sleep(.01)
 assert storage.record(sid)['state']=='aborted';auto(sid)
 checks.append('ONE_SIDED_SPACE_STOP_AND_LEASE')
 # Preview rejects concurrent file changes; preserve checkpoint and model.
 d,sid=directory()
 with patch.object(storage,'snapshot',ample):offline.generate(d,sid,32,[dict(type='add',count=1)])
 storage.burn(sid,'terminal test',stopped=True);doc=preview(sid)
 (d/'S0/input.json').write_text('{}')
 expect('CLEAN_PREVIEW_CHANGED',lambda:apply(doc));auto(sid)
 expect('SESSION_UNKNOWN',lambda:preview(secrets.token_hex(16)))
 result=dict(cleanup_observation=result,status='PASS_CHANGED_STORAGE_LIFECYCLE',checks=checks,checkpoint_preserved=True,grandchildren_stopped=True,restored_copy_rejected=True,ledger_reset=False)
 (OUT/'storage-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
