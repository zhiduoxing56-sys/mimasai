"""Changed deployment writer and fault metadata only; no protocol execution."""
import errno,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.deployment import atomic
from src.deployment_diagnostics import failure,filtered
from src import role_broker,isolated_actor,storage
from src.mpc import ProtocolError
from scripts import local_deployment

class Checks(unittest.TestCase):
 def test_public_plan_and_template_mode_survive_service_umask(self):
  with tempfile.TemporaryDirectory() as tmp:
   previous=os.umask(0o077)
   try:
    for name in ('public-plan.json','job-template.json'):
     path=Path(tmp)/name;atomic(path,dict(public_fixture=True),0o444)
     self.assertEqual(path.stat().st_mode&0o777,0o444)
     self.assertEqual(json.loads(path.read_text()),dict(public_fixture=True))
   finally:os.umask(previous)
 def test_private_metadata_is_0600_under_permissive_umask(self):
  with tempfile.TemporaryDirectory() as tmp:
   previous=os.umask(0)
   try:
    path=Path(tmp)/'private.json';atomic(path,dict(private_fixture=True))
    self.assertEqual(path.stat().st_mode&0o777,0o600)
   finally:os.umask(previous)
 def test_diagnostics_omit_exception_value_and_filename(self):
  secret='SECRET_VALUE_NEVER_PERSIST'
  try:raise PermissionError(errno.EACCES,secret,'/private/'+secret)
  except PermissionError as error:doc=failure(error)
  self.assertNotIn(secret,json.dumps(doc));self.assertEqual(doc['errno'],13)
  self.assertEqual(filtered(dict(doc,unexpected_secret=secret)),doc)
  self.assertIsNone(filtered(dict(doc,source_file='/private/'+secret)))
 def test_actor_failure_is_saved_without_stderr_or_extra_payload(self):
  sid='a'*32;secret='SECRET_VALUE_NEVER_PERSIST'
  output=json.dumps(dict(actor_error='ROLE_OPERATION_FAILED',actor_diagnostic=dict(type='PermissionError',errno=13,source_file='isolated_actor.py',source_line=34,private=secret),secret=secret))
  proc=SimpleNamespace(returncode=1,communicate=lambda **kwargs:(output,secret))
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(role_broker,'ADMIN',Path(tmp)),patch.object(role_broker,'spawn',return_value=proc),patch.object(role_broker,'quiescent'),patch.object(role_broker,'stop'),patch.object(role_broker,'codehash',return_value='fixture'):
    with self.assertRaisesRegex(ProtocolError,'ROLE_OPERATION_FAILED'):role_broker.actor('dealer','offline',sid)
   path=Path(tmp)/(sid+'-dealer-offline-failure.json');value=json.loads(path.read_text())
   self.assertNotIn(secret,json.dumps(value));self.assertEqual(value['diagnostic']['errno'],13);self.assertEqual(path.stat().st_mode&0o777,0o600)
 def test_dealer_partial_cleanup_requires_terminal_stop_and_keeps_ids(self):
  sid='b'*32
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp);(directory/'S0/ring-preprocessing/0').mkdir(parents=True);(directory/'S1').mkdir()
   files=(directory/'S0/ring-preprocessing/0/a.bin',directory/'S1/preprocessing.json')
   for path in files:path.write_bytes(b'synthetic one-shot material')
   retained=directory/'material-identifiers.json';retained.write_text('{"batch":"synthetic-id"}')
   for state,stopped in (('running',True),('unknown',True),('aborted',False)):
    with patch.object(isolated_actor,'own_role',return_value='dealer'),patch.object(isolated_actor,'directory',return_value=directory),patch.object(isolated_actor,'policy',return_value={}),patch.object(storage,'record',return_value=dict(state=state)),patch.object(storage,'stopped',return_value=stopped):
     with self.assertRaisesRegex(ProtocolError,'ACTOR_CLEAN_STATE'):isolated_actor.operation('clean_preview',sid)
   with patch.object(isolated_actor,'own_role',return_value='dealer'),patch.object(isolated_actor,'directory',return_value=directory),patch.object(isolated_actor,'policy',return_value={}),patch.object(storage,'record',return_value=dict(state='cleaned')),patch.object(storage,'stopped',return_value=True):
    preview=isolated_actor.operation('clean_preview',sid);self.assertEqual(len(preview['files']),2)
    result=isolated_actor.operation('clean_apply',sid,expected=preview['digest'])
   self.assertEqual(result['removed_files'],2);self.assertFalse(any(path.exists() for path in files));self.assertTrue(retained.exists())
 def test_old_deployment_acceptance_cannot_start_new_validation_query(self):
  old=dict(status='PASS_REAL_UID_MATRIX',roles=[dict(role=role,checks=[]) for role in ('s0','s1','dealer','receiver','coordinator','page')])
  with patch.object(local_deployment,'call',return_value={'permissions':old}),patch.object(local_deployment,'Client') as client,patch.object(local_deployment,'query') as query:
   with self.assertRaisesRegex(RuntimeError,'UPDATED_DEPLOYMENT_REQUIRED'):local_deployment.validate()
   client.assert_not_called();query.assert_not_called()

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 out=Path(__file__).resolve().parents[1]/'results/local-page';out.mkdir(parents=True,exist_ok=True)
 (out/'deployment-mode-tests.json').write_text(json.dumps(dict(status='PASS_CHANGED_DEPLOYMENT_MODES' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),scope='Real temporary-file mode checks under service umask; synthetic actor fault metadata; no cryptographic protocol, real role UID acceptance pending updated deployment'),indent=2)+'\n')
 sys.exit(0 if result.wasSuccessful() else 1)
