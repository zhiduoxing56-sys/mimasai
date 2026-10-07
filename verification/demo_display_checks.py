"""Changed public display/assets only; no training, materials or real query."""
import copy,contextlib,http.client,json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import demo_page,demo_assets,public_projection
from src.mpc import ProtocolError
from scripts import build_demo_assets,demo_preview
ROOT=Path(__file__).resolve().parents[1]
read=lambda name:json.loads((ROOT/name).read_text())
class Checks(unittest.TestCase):
 def test_projection_drops_unreviewed_data_recursively(self):
  rep=read('docs/representative-results.json');control=read('docs/storage-delivery-results.json');public=read('ui/model-public.json')
  def inject(v):
   if isinstance(v,dict):
    for x in list(v.values()):inject(x)
    v['private_path']='PRIVATE_CANARY';v['secret_shares']=['PRIVATE_CANARY']
   elif isinstance(v,list):
    for x in v:inject(x)
  inject(rep);inject(control)
  value=demo_assets.training_summary(rep,control,public,[dict(report='representative',sha256='a'*64)])
  self.assertNotIn('PRIVATE_CANARY',json.dumps(value));self.assertNotIn('confusion',json.dumps(value));self.assertNotIn('predictions',json.dumps(value))
 def test_actual_metrics_and_curve_are_existing_records(self):
  data=read('ui/training-public.json');rep=read('docs/representative-results.json');demo_assets.validate_training(data)
  self.assertEqual(data['actual']['loss_curve'],rep['actual_training']['loss_curve']);self.assertEqual(len(data['actual']['loss_curve']),160)
  self.assertEqual(data['actual']['metrics']['test']['count'],22);self.assertEqual(round(data['actual']['metrics']['test']['accuracy']*22),18)
  self.assertEqual(data['actual']['metrics']['validation']['classes'][2]['recall'],0)
  self.assertEqual(data['selection']['reference_budget'],320);self.assertFalse(data['selection']['test_used'])
 def test_asset_schema_refuses_private_extra_bad_numbers_order_and_conditions(self):
  original=read('ui/training-public.json')
  changes=[lambda d:d['actual']['metrics']['test'].update(shares=[123]),lambda d:d['actual']['loss_curve'][0].update(preupdate_loss=float('nan')),lambda d:d['classes'].reverse(),lambda d:d['comparisons'][0].update(iterations=640)]
  for mutate in changes:
   data=copy.deepcopy(original);mutate(data)
   with self.assertRaises(ProtocolError):demo_assets.validate_training(data)
  data=copy.deepcopy(original);data['actual']['loss_curve']=[];demo_assets.validate_training(data)
 def test_safety_projection_keeps_separate_space_measures_and_no_ids_of_materials(self):
  data=read('ui/safety-public.json');demo_assets.validate_safety(data)
  self.assertEqual(sum(r['checks'] for r in data['audit']['roles']),140)
  self.assertFalse(data['requests'][1]['has_result']);self.assertIsNone(data['requests'][1]['cost']['wire_bytes'])
  for row in data['cleanup']:
   self.assertEqual(row['space_after']['host_available_bytes']-row['space_before']['host_available_bytes'],0)
  self.assertNotEqual(data['cleanup'][0]['deleted_file_allocated_bytes'],data['cleanup'][0]['space_after']['internal_available_bytes']-data['cleanup'][0]['space_before']['internal_available_bytes'])
  self.assertIs(data['independence']['ring_material_ids_disjoint'],True);self.assertNotIn('ring_material_ids"',json.dumps(data));self.assertNotIn('identifiers',json.dumps(data));self.assertNotIn('probabilities',json.dumps(data))
  bad=copy.deepcopy(data);bad['audit']['roles'][0]['secret']='PRIVATE_CANARY'
  with self.assertRaises(ProtocolError):demo_assets.validate_safety(bad)
 def test_new_routes_only_read_fixed_public_assets(self):
  calls=[];original=Path.read_text
  def audited(path,*args,**kwargs):
   self.assertTrue(path.resolve().is_relative_to((ROOT/'ui').resolve()),str(path));calls.append(path.name);return original(path,*args,**kwargs)
  with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'read_text',audited),patch.object(demo_page.Page,'backend',side_effect=OSError('offline')):
   server=demo_page.server(0,ROOT/'ui',Path(tmp)/'page.sqlite');t=threading.Thread(target=server.serve_forever);t.start()
   try:
    c=http.client.HTTPConnection('127.0.0.1',server.server_port)
    for route in ('/','/training','/privacy','/common.js','/training.js','/privacy.js','/training-public.json','/safety-public.json'):
     c.request('GET',route);r=c.getresponse();self.assertEqual(r.status,200);data=r.read();self.assertNotIn(b'__PUBLIC_',data);self.assertNotIn(b'__DISPLAY_CONTEXT__',data)
    for route in ('/api/fault','/api/read','/results/local-page/query-success.json','/verification/','/training?path=/etc/shadow','/../state/mpc/S0-ledger.sqlite'):
     c.request('GET',route);r=c.getresponse();self.assertIn(r.status,(403,404));r.read()
    c.close()
   finally:server.shutdown();t.join();server.server_close()
  self.assertTrue({'training-public.json','safety-public.json'}.issubset(calls))
 def test_existing_query_http_contract_unchanged_with_retained_response(self):
  result=read('results/local-page/query-success.json')['result'];operations=[]
  def backend(page,action,**kw):
   operations.append((action,kw))
   if action=='overview':return dict(connected=True)
   if action=='authorize':return dict(authorized=True)
   return result
  with tempfile.TemporaryDirectory() as tmp,patch.object(demo_page.Page,'backend',backend):
   server=demo_page.server(0,ROOT/'ui',Path(tmp)/'page.sqlite');t=threading.Thread(target=server.serve_forever);t.start()
   try:
    port=server.server_port;c=http.client.HTTPConnection('127.0.0.1',port);c.request('GET','/api/overview');r=c.getresponse();cookie=r.getheader('Set-Cookie').split(';')[0];overview=json.loads(r.read())
    h={'Cookie':cookie,'Origin':f'http://127.0.0.1:{port}','Content-Type':'application/json','X-PGNN-CSRF':overview['csrf']}
    c.request('POST','/api/login',json.dumps(dict(access='a'*64)),h);r=c.getresponse();self.assertEqual(r.status,200);r.read()
    c.request('POST','/api/status',json.dumps(dict(token='b'*32)),h);r=c.getresponse();self.assertEqual(json.loads(r.read()),public_projection.status(result,read('ui/model-public.json')))
    before=len(operations)
    for extra in ('node','target','receiver','model','path','command'):
     c.request('POST','/api/submit',json.dumps(dict(token='b'*32,**{extra:'untrusted'})),h);r=c.getresponse();self.assertEqual(r.status,409);r.read()
    self.assertEqual(before,len(operations));self.assertEqual(operations[-1][0],'status');self.assertEqual(set(operations[-1][1]),{'client','token'});c.close()
   finally:server.shutdown();t.join();server.server_close()
 def test_pending_preview_is_readonly_and_has_no_backend(self):
  with tempfile.TemporaryDirectory() as tmp:
   server=demo_page.server(0,ROOT/'ui',Path(tmp)/'page.sqlite',display_mode='pending_deployment');server.RequestHandlerClass=demo_preview.Preview;t=threading.Thread(target=server.serve_forever);t.start()
   try:
    c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET','/');r=c.getresponse();self.assertIn(b'pending_deployment',r.read())
    c.request('POST','/api/submit','{}');r=c.getresponse();self.assertEqual(r.status,409);self.assertEqual(json.loads(r.read()),dict(error='PREVIEW_READ_ONLY'));c.close()
   finally:server.shutdown();t.join();server.server_close()
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks));out=ROOT/'results/demo-final';out.mkdir(parents=True,exist_ok=True)
 (out/'display-short-tests.json').write_text(json.dumps(dict(status='PASS_DISPLAY_CHANGED_SURFACES' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),scope='Independent public assets/routes and retained-result HTTP rendering; synthetic adapter, no real UID acceptance or new cryptographic query',materials_generated=False,training_executed=False),indent=2)+'\n');sys.exit(0 if result.wasSuccessful() else 1)
