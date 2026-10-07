"""Temporary browser adapter for existing public acceptance records, no MPC.

This is a display test fixture, never installed or used by the page service.
Status tokens are public fixture names; authorization uses a public zero value
and a temporary page DB. Backend methods never call the real role interface.
"""
import copy,json,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import demo_page
from src.mpc import require,ProtocolError
ROOT=Path(__file__).resolve().parents[1]
SUCCESS=json.loads((ROOT/'results/local-page/query-success.json').read_text())['result']
FAILURE=json.loads((ROOT/'results/local-page/query-failure.json').read_text())['result']
COUNTS={'overview':0,'authorize':0,'status':0,'submit':0};LOCK=threading.Lock()
class Fixture(demo_page.Page):
 def backend(self,action,**args):
  with LOCK:COUNTS[action]+=1
  if action=='overview':return dict(connected=True)
  if action=='authorize':require(args['access']=='0'*64,'FIXTURE_ACCESS');return dict(authorized=True)
  if action=='status':
   require(args['token'] in ('a'*32,'b'*32),'REQUEST_CAPABILITY_REJECTED');return copy.deepcopy(SUCCESS if args['token']=='a'*32 else FAILURE)
  raise ProtocolError('DISPLAY_TEST_NO_QUERY')
 def do_GET(self):
  if self.path=='/test-evidence':
   self.validate_host();return self.reply(200,dict(kind='INDEPENDENT_BROWSER_RETAINED_RECORD_ADAPTER',calls=COUNTS.copy(),real_backend_connected=False,materials_generated=False,training_executed=False))
  super().do_GET()
def main():
 with tempfile.TemporaryDirectory(prefix='pgnn-display-test-') as temp:
  with demo_page.server(8767,ROOT/'ui',Path(temp)/'page.sqlite',display_mode='record_validation') as server:
   server.RequestHandlerClass=Fixture;print('Read-only retained-record browser fixture on 127.0.0.1:8767; no real backend.',flush=True)
   try:server.serve_forever()
   except KeyboardInterrupt:pass
if __name__=='__main__':main()
