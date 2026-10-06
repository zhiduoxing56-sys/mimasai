"""Short changed-surface checks. Synthetic fixtures, never new model training."""
import contextlib,hashlib,http.client,json,os,secrets,sqlite3,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import demo_page,demo_coordinator,storage,public_projection
from src.mpc import ProtocolError
from scripts import install_local_roles as installer
PROJECT=Path(__file__).resolve().parents[1]
PUBLIC=json.loads((PROJECT/'ui/model-public.json').read_text())

class Checks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_recursive_result_allowlist_and_incomplete_refusal(self):
  sid='a'*32;values=[1.0]+[0.0]*(len(PUBLIC['classes'])-1)
  final=dict(request_id=sid,model_id=PUBLIC['model_id'],classes=PUBLIC['classes'],secret='MUST_NOT_LEAVE',results=[dict(node_id=PUBLIC['allowed_targets'][0],probabilities=values,predicted_class=PUBLIC['classes'][0],shares=[999])])
  value=dict(request_id=sid,phase='complete',terminal=True,delivery_state='complete',result=final,cost=dict(wall_seconds=1,wire_bytes=2,rounds=3,ledger='MUST_NOT_LEAVE'),error=None)
  output=public_projection.status(value,PUBLIC);self.assertNotIn('MUST_NOT_LEAVE',json.dumps(output));self.assertNotIn('shares',json.dumps(output))
  value['delivery_state']='incomplete'
  with self.assertRaisesRegex(ProtocolError,'PUBLIC_INCOMPLETE_RESULT'):public_projection.status(value,PUBLIC)
 def test_metadata_comes_from_existing_model(self):
  report=json.loads((PROJECT/f'results/application/{PUBLIC["experiment_id"]}/manifest.json').read_text())
  self.assertEqual(public_projection.model(report),PUBLIC);self.assertEqual(PUBLIC['nodes'],64);self.assertEqual(PUBLIC['source_iteration'],160)
  from src.application import inference_plan
  filtered=public_projection.planning_report(report)
  self.assertEqual(inference_plan(report,'he','fss',PUBLIC['allowed_targets']),inference_plan(filtered,'he','fss',PUBLIC['allowed_targets']))
  self.assertNotIn('online',filtered['publication']);self.assertNotIn('offline',filtered['publication']);self.assertNotIn('training_report',filtered)
 def test_http_disconnect_routes_authorization_and_binding(self):
  with patch.object(demo_page.Page,'backend',side_effect=OSError('not deployed')):
   server=demo_page.server(0,PROJECT/'ui',self.path/'page.sqlite');thread=threading.Thread(target=server.serve_forever);thread.start()
   try:
    port=server.server_port;conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
    conn.request('GET','/api/overview');response=conn.getresponse();cookie=response.getheader('Set-Cookie').split(';')[0];overview=json.loads(response.read())
    self.assertFalse(overview['connected']);self.assertNotIn('result',overview);self.assertEqual(overview['model'],PUBLIC)
    for route in ('/../../src/mpc.py','/api/overview?path=/etc/shadow','/state/mpc/S0-ledger.sqlite'):
     conn.request('GET',route,headers={'Cookie':cookie});response=conn.getresponse();self.assertIn(response.status,(403,404));response.read()
    conn.request('GET','/',headers={'Host':'evil.example'});response=conn.getresponse();self.assertEqual(response.status,403);response.read()
    def post(route,data,**headers):
     conn.request('POST',route,json.dumps(data),headers=dict({'Cookie':cookie,'Content-Type':'application/json','Origin':f'http://127.0.0.1:{port}','X-PGNN-CSRF':overview['csrf']},**headers));r=conn.getresponse();return r.status,json.loads(r.read())
    self.assertEqual(post('/api/submit',dict(token='a'*32))[0],403)
    self.assertEqual(post('/api/login',dict(access='a'*64),**{'Origin':'http://evil.example'})[0],403)
    self.assertEqual(post('/api/login',dict(access='a'*64),**{'X-PGNN-CSRF':'wrong'})[0],403)
    with patch.object(demo_page.Page,'backend',return_value={'authorized':True}):self.assertEqual(post('/api/login',dict(access='a'*64))[0],200)
    for extra in ('path','command','target','receiver','model'):
     self.assertEqual(post('/api/submit',dict(token='a'*32,**{extra:'untrusted'}))[0],409)
    with patch.object(demo_page.Page,'backend',side_effect=ProtocolError('REQUEST_CAPABILITY_REJECTED')):
     self.assertEqual(post('/api/status',dict(token='b'*32)),(409,{'error':'REQUEST_CAPABILITY_REJECTED'}))
    conn.close()
   finally:server.shutdown();thread.join();server.server_close()
 def test_coordinator_duplicate_persists_and_other_client_is_denied(self):
  (self.path/'state').mkdir();client='a'*48;token='b'*32;access='c'*64
  class NoWorker:
   def __init__(self,**kwargs):pass
   def start(self):pass
  with patch.object(demo_coordinator,'root',return_value=self.path),patch.object(demo_coordinator,'connected',return_value=True),patch.object(demo_coordinator,'policy',return_value={'access_sha256':hashlib.sha256(access.encode()).hexdigest()}),patch.object(demo_coordinator.threading,'Thread',NoWorker):
   demo_coordinator.command(dict(action='authorize',client=client,access=access))
   demo_coordinator.command(dict(action='authorize',client='d'*48,access=access))
   try:
    first=demo_coordinator.command(dict(action='submit',client=client,token=token))
    self.assertEqual(first,demo_coordinator.command(dict(action='submit',client=client,token=token)))
    self.assertEqual(first,demo_coordinator.command(dict(action='status',client=client,token=token)))
    with self.assertRaisesRegex(ProtocolError,'REQUEST_CAPABILITY_REJECTED'):demo_coordinator.command(dict(action='status',client='d'*48,token=token))
    with self.assertRaisesRegex(ProtocolError,'QUERY_BUSY'):demo_coordinator.command(dict(action='submit',client=client,token='e'*32))
    with contextlib.closing(demo_coordinator.db()) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM queries').fetchone()[0],1)
   finally:demo_coordinator.ACTIVE.release()
 def test_gate_space_refusal_and_cleaned_material_tombstone(self):
  (self.path/'gate').mkdir();cfg=storage.policy()
  with patch.dict(os.environ,PGNN_GATE_DIR=str(self.path/'gate')):
   for internal,host,code in ((0,1<<60,'INTERNAL_SPACE_LOW'),(1<<60,0,'HOST_SPACE_LOW'),(1<<60,None,'HOST_SPACE_UNKNOWN')):
    with self.assertRaisesRegex(ProtocolError,code):storage.check(self.path,0,probe=lambda *args:dict(internal_available_bytes=internal,host_available_bytes=host),cfg=cfg)
   with contextlib.closing(storage.db()) as db,db:db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)',('a'*32,str(self.path),'b'*32,'cleaned',0,'{}'))
   with self.assertRaisesRegex(ProtocolError,'SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE'):storage.reject_burned('b'*32)
 def test_migration_preserves_inode_and_recovers_after_rename(self):
  admin=self.path/'admin';admin.mkdir();source=self.path/'ledger.sqlite';target=self.path/'retained.sqlite';source.write_bytes(b'synthetic durable state')
  history=dict(state_files=[]);installer.atomic(admin/'migration.json',history);inode=source.stat().st_ino
  account=type('Identity',(),{'pw_uid':os.getuid(),'pw_gid':os.getgid()})();group=type('Group',(),{'gr_gid':os.getgid()})()
  with patch.object(installer,'BASE',self.path),patch.object(installer.pwd,'getpwnam',return_value=account),patch.object(installer.grp,'getgrnam',return_value=group):
   # Emulate interruption after rename, before link and completion journal.
   before=dict(path=str(source),device=source.stat().st_dev,inode=inode,bytes=source.stat().st_size,sha256=installer.sha(source))
   row=dict(before=before,after={'path':str(target)},content_preserved=False,phase='planned');history['state_files'].append(row);installer.atomic(admin/'migration.json',history);source.rename(target)
   installer.migrate(source,target,'s0',history['state_files'])
   self.assertTrue(source.is_symlink());self.assertEqual(target.stat().st_ino,inode);self.assertEqual(target.read_bytes(),b'synthetic durable state');self.assertTrue(row['content_preserved'])
 def test_restart_keeps_unconfirmed_stop_and_burns_running_gate(self):
  (self.path/'state').mkdir();gate=self.path/'gate';gate.mkdir();sid='f'*32;token='b'*32;client='a'*48
  document=dict(request_id=sid,phase='stopping',terminal=True,delivery_state='incomplete',result=None,cost=None,error='STOP_UNCONFIRMED')
  prior=demo_coordinator.STOPPED
  with patch.dict(os.environ,PGNN_GATE_DIR=str(gate)),patch.object(demo_coordinator,'root',return_value=self.path):
   with contextlib.closing(storage.db()) as db,db:db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)',(sid,str(self.path),'d'*32,'running',0,''))
   with contextlib.closing(demo_coordinator.db()) as db,db:db.execute('INSERT INTO queries VALUES (?,?,?,?)',(token,client,sid,json.dumps(document)))
   try:
    demo_coordinator.STOPPED=False;demo_coordinator.recover_pending();self.assertTrue(demo_coordinator.STOPPED);self.assertEqual(storage.record(sid)['state'],'stopping');self.assertFalse(storage.stopped(sid))
    with self.assertRaisesRegex(ProtocolError,'SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE'):storage.reject_burned('d'*32)
   finally:demo_coordinator.STOPPED=prior

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks);result=unittest.TextTestRunner(verbosity=2).run(suite)
 report=dict(status='PASS_CHANGED_SURFACES' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),scope='Independent short HTTP and metadata/lifecycle tests with synthetic fixtures; not real UID or cryptographic backend acceptance',long_training=False)
 (PROJECT/'results/local-page/short-tests.json').write_text(json.dumps(report,indent=2)+'\n');sys.exit(0 if result.wasSuccessful() else 1)
