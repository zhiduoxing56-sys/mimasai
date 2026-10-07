"""Short fault-recording checks with synthetic metadata; no cryptographic run."""
import json,os,sqlite3,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_local_query import diagnose
from scripts import local_deployment

class Checks(unittest.TestCase):
 def test_read_only_diagnostic_omits_capabilities_and_private_values(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'gate').mkdir();(base/'actors/coordinator/state').mkdir(parents=True);(base/'config').mkdir()
   sid='a'*32;secret='DO_NOT_DISCLOSE_PRIVATE_DATA'
   (base/'config/source-manifest.json').write_text(json.dumps(dict(commit='test-fixture')))
   with sqlite3.connect(base/'gate/sessions.sqlite') as conn:
    conn.execute('CREATE TABLE sessions(sid,state,batch,budget,detail)');conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(sid,'cleaned','b'*32,1024,secret))
    conn.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,sid,body)')
    conn.execute('INSERT INTO events(sid,body) VALUES(?,?)',(sid,json.dumps(dict(stage='admission',status='failed',reason='ROLE_OPERATION_FAILED:'+secret,shares=secret))))
    conn.execute('INSERT INTO events(sid,body) VALUES(?,?)',(sid,json.dumps(dict(stage='termination',proof=dict(stopped=True,private=secret)))))
    conn.execute('INSERT INTO events(sid,body) VALUES(?,?)',(sid,json.dumps(dict(stage='cleanup_observation',observation=dict(deleted_file_allocated_bytes=4096,reclaimable_upper_bytes=8192,space_before=dict(internal_available_bytes=10000,host_available_bytes=None,host_status='UNKNOWN',host_error=secret),space_after=dict(internal_available_bytes=14096,host_available_bytes=20000,host_status='READABLE'))))))
   with sqlite3.connect(base/'actors/coordinator/state/queries.sqlite') as conn:
    conn.execute('CREATE TABLE queries(token,client,sid,document)')
    conn.execute('INSERT INTO queries VALUES(?,?,?,?)',(secret,secret,sid,json.dumps(dict(request_id=sid,phase='failed',terminal=True,delivery_state='incomplete',error='ROLE_OPERATION_FAILED',result={'secret':secret},cost={'wire_bytes':0,'private':secret}))))
   paths=(base/'gate/sessions.sqlite',base/'actors/coordinator/state/queries.sqlite');before=[p.read_bytes() for p in paths]
   value=diagnose(sid,base,base)
   self.assertNotIn(secret,json.dumps(value));self.assertEqual(value['failure']['reason'],'ROLE_OPERATION_FAILED');self.assertTrue(value['lifecycle'][1]['stopped'])
   self.assertIsNone(value['lifecycle'][2]['space']['space_before']['host_available_bytes']);self.assertEqual(value['lifecycle'][2]['space']['deleted_file_allocated_bytes'],4096)
   self.assertEqual(before,[p.read_bytes() for p in paths]);self.assertFalse(value['state_modified']);self.assertFalse(value['protocol_executed'])
 def test_unknown_session_refuses_without_creating_database(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'gate').mkdir()
   with self.assertRaises(sqlite3.OperationalError):diagnose('a'*32,base,base)
   self.assertFalse((base/'gate/sessions.sqlite').exists())
 def test_unexpected_query_failure_is_saved_before_validation_rejection(self):
  sid='c'*32;token='d'*32;cookie='PRIVATE_VIEW_CAPABILITY'
  terminal=dict(request_id=sid,phase='failed',terminal=True,delivery_state='incomplete',result=None,error='ROLE_OPERATION_FAILED')
  class Client:
   jar=[SimpleNamespace(name='pgnn-client',value=cookie)]
   def api(self,path,data):return terminal.copy()
  proof=dict(session=sid,state='cleaned',identifiers=None,report=None)
  reuse=dict(rejected=True,protocol_reexecuted=False)
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);out=base/'results/local-page'
   with patch.object(local_deployment,'ROOT',base),patch.object(local_deployment,'OUT',out),patch.object(local_deployment.secrets,'token_hex',return_value=token),patch.object(local_deployment,'call',side_effect=[proof,reuse]):
    with self.assertRaisesRegex(RuntimeError,'UNEXPECTED_QUERY_OUTCOME'):local_deployment.query(Client())
   value=json.loads((out/('query-attempt-'+sid+'.json')).read_text())
   self.assertEqual(value['result'],terminal);self.assertEqual(value['backend_evidence'],proof);self.assertTrue(value['post_cleanup_reuse']['rejected']);self.assertFalse(value['automatic_protocol_retry'])
   self.assertNotIn(cookie,json.dumps(value));self.assertNotIn(token,json.dumps(value));self.assertFalse((out/'query-success.json').exists())
   private=base/'results/page/browser-session.json';self.assertEqual(private.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(private.read_text())['failure']['token'],token)
 def test_status_transport_failure_retains_pending_session_without_retry(self):
  sid='e'*32;pending=dict(request_id=sid,phase='online',terminal=False,delivery_state='pending',result=None,error=None)
  class Client:
   jar=[]
   def __init__(self):self.submits=0
   def api(self,path,data):
    if path=='/api/status':raise OSError('transport interrupted')
    self.submits+=1;return pending.copy()
  client=Client()
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);out=base/'results/local-page'
   with patch.object(local_deployment,'ROOT',base),patch.object(local_deployment,'OUT',out),patch.object(local_deployment,'call') as broker:
    with self.assertRaises(OSError):local_deployment.query(client)
   value=json.loads((out/('query-attempt-'+sid+'.json')).read_text());self.assertEqual(value['result'],pending);self.assertFalse(value['automatic_protocol_retry']);self.assertEqual(client.submits,2);broker.assert_not_called()
   self.assertEqual(json.loads((base/'results/page/browser-session.json').read_text())['pending']['request_id'],sid)
 def test_submit_response_loss_keeps_capability_without_new_request(self):
  token='f'*32
  class Client:
   jar=[SimpleNamespace(name='pgnn-client',value='PRIVATE_COOKIE')]
   def api(self,path,data):raise OSError('submit response lost')
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp)
   with patch.object(local_deployment,'ROOT',base),patch.object(local_deployment.secrets,'token_hex',return_value=token),patch.object(local_deployment,'call') as broker:
    with self.assertRaises(OSError):local_deployment.query(Client())
   private=json.loads((base/'results/page/browser-session.json').read_text());self.assertEqual(private['pending']['token'],token);self.assertIsNone(private['pending']['request_id']);broker.assert_not_called()

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks);result=unittest.TextTestRunner(verbosity=2).run(suite)
 out=Path(__file__).resolve().parents[1]/'results/local-page';out.mkdir(parents=True,exist_ok=True)
 (out/'diagnostic-short-tests.json').write_text(json.dumps(dict(status='PASS_CHANGED_DIAGNOSTICS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),scope='Synthetic read-only metadata and operator transport fault checks; no cryptographic protocol or real UID acceptance'),indent=2)+'\n')
 sys.exit(0 if result.wasSuccessful() else 1)
