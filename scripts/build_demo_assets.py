"""Offline audit of existing public reports into read-only page assets. No MPC."""
import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.demo_assets import training_summary,safety_summary
ROOT=Path(__file__).resolve().parents[1]
SOURCES={'representative':'docs/representative-results.json','storage_delivery':'docs/storage-delivery-results.json','real_uid':'results/local-page/real-uid-permissions-cf7da5b3c1929bbc299a7ad1a688035d4ba88643e453fed8b43add54dd972509.json','query_success':'results/local-page/query-success.json','query_failure':'results/local-page/query-failure.json','independence':'results/local-page/request-independence.json'}
def build():
    docs={};digests={}
    for name,relative in SOURCES.items():
        path=ROOT/relative
        if path.is_symlink() or not path.is_file():raise RuntimeError('Expected regular public source: '+relative)
        raw=path.read_bytes();docs[name]=json.loads(raw);digests[name]=dict(report=name,sha256=hashlib.sha256(raw).hexdigest())
    public=json.loads((ROOT/'ui/model-public.json').read_text())
    assets={'training-public.json':training_summary(docs['representative'],docs['storage_delivery'],public,[digests[n] for n in ('representative','storage_delivery')]),
        'safety-public.json':safety_summary(docs['real_uid'],docs['query_success'],docs['query_failure'],docs['independence'],[digests[n] for n in ('real_uid','query_success','query_failure','independence')])}
    records=[]
    for name,value in assets.items():
        path=ROOT/'ui'/name
        if path.exists():os.chmod(path,0o600)
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.chmod(path,0o444)
        records.append(dict(path='ui/'+name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest=dict(kind='OFFLINE_ALLOWLISTED_PUBLIC_ASSETS',sources=[dict(path=SOURCES[name],**value) for name,value in digests.items()],assets=records,training_executed=False,materials_generated=False,private_reports_opened=False,scope='Existing public aggregate metrics/loss curve and acceptance metadata only; page never opens source reports')
    (ROOT/'docs/demo-public-assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status='PASS_PUBLIC_ASSET_AUDIT',assets=records,training=False,materials=False)))
if __name__=='__main__':build()
