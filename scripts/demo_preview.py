"""Loopback readonly preview of pending UI; no backend connection or POST actions."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import demo_page
PROJECT=Path(__file__).resolve().parents[1]
class Preview(demo_page.Page):
    def backend(self,*args,**kwargs):raise OSError('READ_ONLY_PENDING_PREVIEW')
    def do_POST(self):self.reply(409,dict(error='PREVIEW_READ_ONLY'))
def main():
    with tempfile.TemporaryDirectory(prefix='pgnn-demo-preview-') as temp:
        with demo_page.server(8766,PROJECT/'ui',Path(temp)/'page.sqlite',display_mode='pending_deployment') as server:
            server.RequestHandlerClass=Preview
            print(json.dumps(dict(mode='READ_ONLY_PENDING_DEPLOYMENT_PREVIEW',url='http://127.0.0.1:8766/',query_backend_connected=False,materials_generated=False,scope='Operator preview, not real page UID deployment acceptance')),flush=True)
            try:server.serve_forever()
            except KeyboardInterrupt:pass
if __name__=='__main__':main()
