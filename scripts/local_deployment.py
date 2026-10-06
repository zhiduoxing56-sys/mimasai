"""Operator-side fixed-action validation. Never reads role-private directories."""
import argparse,http.cookiejar,json,secrets,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.deployment import BROKER,call,hexid
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/local-page'
def store(name,document):
 OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_text(json.dumps(document,indent=2,ensure_ascii=False)+'\n')
def audit():
 matrix=call(BROKER,dict(action='audit'));evidence=call(BROKER,dict(action='evidence'));store('real-uid-permissions.json',matrix);store('migration-evidence.json',evidence['migration'])
 print(json.dumps(dict(status=matrix['status'],roles=len(matrix['roles']),checks=sum(len(r['checks']) for r in matrix['roles']),evidence=str(OUT/'real-uid-permissions.json'))))
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
 token=secrets.token_hex(16);started=time.perf_counter();first=client.api('/api/submit',dict(token=token));repeated=client.api('/api/submit',dict(token=token));assert repeated['request_id']==first['request_id'];stages=[];last=None;deadline=time.monotonic()+300
 while True:
  last=client.api('/api/status',dict(token=token))
  if not stages or stages[-1]['phase']!=last['phase']:stages.append(dict(phase=last['phase'],elapsed_seconds=time.perf_counter()-started));print(json.dumps(dict(request_id=last['request_id'],phase=last['phase'])),flush=True)
  if last['terminal']:break
  if time.monotonic()>deadline:raise RuntimeError('Query validation timeout: keep materials and request evidence; never resubmit a new protocol for this session.')
  time.sleep(.8)
 again=client.api('/api/submit',dict(token=token));assert again==last
 if fault:assert last['result'] is None and last['delivery_state']=='incomplete' and last['error']=='INJECTED_INPUT_PREPARATION_FAILURE'
 else:assert last['delivery_state']=='complete' and last['result'] is not None
 proof=call(BROKER,dict(action='query_evidence',sid=last['request_id']));reuse=call(BROKER,dict(action='reuse_probe',sid=last['request_id']));assert reuse['rejected'] and not reuse['protocol_reexecuted']
 record=dict(kind='REAL_LOOPBACK_PAGE_API_FAILURE' if fault else 'REAL_LOOPBACK_PAGE_API_QUERY',request_id=last['request_id'],stages=stages,result=last,duplicate_submission_same_request=True,refresh_status_only=True,post_cleanup_reuse=reuse,backend_evidence=proof,training_performed=False)
 store('query-failure.json' if fault else 'query-success.json',record);return proof
def validate():
 client=Client();client.authorize();success=query(client);failure=query(client,True)
 assert success['batch']!=failure['batch'];a=success['identifiers'];b=failure['identifiers']
 assert not set(a['ring_material_ids'])&set(b['ring_material_ids']);assert not {v for row in a['he_mask_ids'] for v in row}&{v for row in b['he_mask_ids'] for v in row}
 store('request-independence.json',dict(status='PASS_REAL_NEW_MATERIALS',sessions=[success['session'],failure['session']],distinct_batches=True,ring_material_ids_disjoint=True,he_mask_ids_disjoint=True,protocol_rerun=False))
 print('PASS: one real query, one real input fault, duplicate submissions and fresh-material separation. No training.')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('audit','validate','evidence'));a=p.parse_args()
 if a.command=='audit':audit()
 elif a.command=='validate':validate()
 else:store('deployment-evidence.json',call(BROKER,dict(action='evidence')));print('Saved deployment evidence; no private roles read by operator.')
if __name__=='__main__':main()
