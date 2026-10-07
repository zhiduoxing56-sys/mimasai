"""Operator-side fixed-action validation. Never reads role-private directories."""
import argparse,http.cookiejar,json,os,secrets,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.deployment import BROKER,call,hexid,atomic
from src.mpc import ProtocolError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/local-page'
def store(name,document):
 OUT.mkdir(parents=True,exist_ok=True);atomic(OUT/name,document)
def browser_session(client,token,sid,view):
 """Private authorized-view capability; never part of public evidence/archive."""
 path=ROOT/'results/page/browser-session.json';path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);previous=json.loads(path.read_text()) if path.exists() else {}
 previous['cookies']=[dict(name=c.name,value=c.value) for c in client.jar]
 previous[view]=dict(token=token,request_id=sid)
 fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as stream:json.dump(previous,stream);stream.flush();os.fsync(stream.fileno())
 os.chmod(path,0o600)
def audit():
 matrix=call(BROKER,dict(action='audit'));evidence=call(BROKER,dict(action='evidence'))
 require_deployment(matrix)
 previous=OUT/'real-uid-permissions.json'
 if previous.exists():
  old=json.loads(previous.read_text());archive=OUT/('real-uid-permissions-'+old['source_sha256']+'.json')
  if not archive.exists():store(archive.name,old)
 previous=OUT/'migration-evidence.json'
 if previous.exists():
  old=json.loads(previous.read_text());archive=OUT/('migration-evidence-'+old['commit']+'.json')
  if not archive.exists():store(archive.name,old)
 store('real-uid-permissions-'+matrix['source_sha256']+'.json',matrix);store('real-uid-permissions.json',matrix);store('migration-evidence.json',evidence['migration'])
 print(json.dumps(dict(status=matrix['status'],roles=len(matrix['roles']),checks=sum(len(r['checks']) for r in matrix['roles']),evidence=str(OUT/'real-uid-permissions.json'))))
def require_deployment(matrix):
 if not matrix or matrix.get('status')!='PASS_REAL_UID_MATRIX':raise RuntimeError('UPDATED_REAL_UID_AUDIT_REQUIRED')
 roles=matrix.get('roles',[])
 if {r['role'] for r in roles}!={'s0','s1','dealer','receiver','coordinator','page'}:raise RuntimeError('UPDATED_REAL_UID_AUDIT_REQUIRED')
 for role in roles:
  resources={c['resource']:c for c in role['checks']}
  for name in ('atomic_public_metadata','atomic_private_metadata'):
   if name not in resources or not resources[name]['pass_check']:raise RuntimeError('UPDATED_DEPLOYMENT_REQUIRED: public atomic mode acceptance is absent')
  if role['role'] in ('s0','s1','dealer'):
   space=role.get('readiness',{}).get('space',{})
   if space.get('host_status')!='READABLE' or space.get('host_available_bytes') is None:raise RuntimeError('ROLE_HOST_SPACE_ACCEPTANCE_REQUIRED')
  if role['role']=='dealer' and 'native_public_metadata' not in role.get('readiness',{}):raise RuntimeError('DEALER_NATIVE_READINESS_REQUIRED')
class Client:
 def __init__(self):
  self.jar=http.cookiejar.CookieJar();self.http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.csrf=None
 def api(self,path,data=None):
  headers={'Origin':'http://127.0.0.1:8765'}
  if data is not None:headers.update({'Content-Type':'application/json','X-PGNN-CSRF':self.csrf})
  request=urllib.request.Request('http://127.0.0.1:8765'+path,json.dumps(data).encode() if data is not None else None,headers)
  with self.http.open(request,timeout=10) as reply:return json.load(reply)
 def authorize(self):
  self.csrf=self.api('/api/overview')['csrf'];access=json.loads((ROOT/'results/page/access-link.json').read_text())['access'];self.api('/api/login',dict(access=access))
  if not self.api('/api/overview')['connected']:raise RuntimeError('Real UID acceptance/backend connection is pending.')
def query(client,fault=False):
 if fault:call(BROKER,dict(action='fault_next'))
 token=secrets.token_hex(16);started=time.perf_counter();browser_session(client,token,None,'pending')
 first=client.api('/api/submit',dict(token=token));sid=hexid(first['request_id'])
 browser_session(client,token,sid,'pending')
 name='query-attempt-'+sid+'.json'
 record=dict(kind='REAL_LOOPBACK_PAGE_API_ATTEMPT',request_id=sid,expected_input_fault=fault,stages=[],result=first,duplicate_submission_same_request=False,refresh_status_only=True,training_performed=False)
 store(name,record)
 try:
  repeated=client.api('/api/submit',dict(token=token));assert repeated['request_id']==sid;record['duplicate_submission_same_request']=True
  deadline=time.monotonic()+300
  while True:
   last=client.api('/api/status',dict(token=token));assert last['request_id']==sid;record['result']=last
   if not record['stages'] or record['stages'][-1]['phase']!=last['phase']:
    record['stages'].append(dict(phase=last['phase'],elapsed_seconds=time.perf_counter()-started));print(json.dumps(dict(request_id=sid,phase=last['phase'])),flush=True)
   store(name,record)
   if last['terminal']:break
   if time.monotonic()>deadline:raise RuntimeError('QUERY_VALIDATION_TIMEOUT')
   time.sleep(.8)
  again=client.api('/api/submit',dict(token=token));assert again==last
  # Persist the failed attempt and its view capability before checking success.
  # Refresh is status-only and never starts the old session again.
  delivered=last['delivery_state']=='complete' and last['result'] is not None
  browser_session(client,token,sid,'success' if delivered else 'failure')
  proof=call(BROKER,dict(action='query_evidence',sid=sid));record['backend_evidence']=proof;store(name,record)
  reuse=call(BROKER,dict(action='reuse_probe',sid=sid));record['post_cleanup_reuse']=reuse;store(name,record)
  assert reuse['rejected'] and not reuse['protocol_reexecuted']
  expected=last['result'] is None and last['delivery_state']=='incomplete' and last['error']=='INJECTED_INPUT_PREPARATION_FAILURE' if fault else delivered
  if not expected:raise RuntimeError('UNEXPECTED_QUERY_OUTCOME: '+str(last.get('error'))+'; evidence='+str(OUT/name))
  record['kind']='REAL_LOOPBACK_PAGE_API_FAILURE' if fault else 'REAL_LOOPBACK_PAGE_API_QUERY';store(name,record)
  store('query-failure.json' if fault else 'query-success.json',record);return proof
 except BaseException as error:
  record['validation_error']=type(error).__name__
  record['automatic_protocol_retry']=False;store(name,record);raise
def validate():
 require_deployment(call(BROKER,dict(action='evidence'))['permissions'])
 client=Client();client.authorize();success=query(client);failure=query(client,True)
 assert success['batch']!=failure['batch'];a=success['identifiers'];b=failure['identifiers']
 assert not set(a['ring_material_ids'])&set(b['ring_material_ids']);assert not {v for row in a['he_mask_ids'] for v in row}&{v for row in b['he_mask_ids'] for v in row}
 store('request-independence.json',dict(status='PASS_REAL_NEW_MATERIALS',sessions=[success['session'],failure['session']],distinct_batches=True,ring_material_ids_disjoint=True,he_mask_ids_disjoint=True,protocol_rerun=False))
 print('PASS: one real query, one real input fault, duplicate submissions and fresh-material separation. No training.')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('audit','validate','evidence','query-evidence','reuse-probe'));p.add_argument('--session');a=p.parse_args()
 if a.command=='audit':audit()
 elif a.command=='validate':validate()
 elif a.command=='query-evidence':
  sid=hexid(a.session);value=call(BROKER,dict(action='query_evidence',sid=sid));store('diagnostic-'+sid+'.json',value);print(json.dumps({k:v for k,v in value.items() if k not in ('identifiers','report')}))
 elif a.command=='reuse-probe':
  sid=hexid(a.session);value=call(BROKER,dict(action='reuse_probe',sid=sid));store('reuse-'+sid+'.json',value);print(json.dumps(value))
 else:store('deployment-evidence.json',call(BROKER,dict(action='evidence')));print('Saved deployment evidence; no private roles read by operator.')
if __name__=='__main__':
 try:main()
 except (RuntimeError,ProtocolError,OSError,ValueError,AssertionError) as error:
  raw=str(error).split(':',1)[0]
  reason=raw if raw and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in raw) else 'LOCAL_VALIDATION_FAILED'
  print(json.dumps(dict(status='VALIDATION_REFUSED_OR_FAILED',reason=reason,error_type=type(error).__name__,automatic_protocol_retry=False)),file=sys.stderr);sys.exit(1)
