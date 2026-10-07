"""Metadata-only post-deployment display check; never submit or execute a query."""
import json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.deployment import CODE,BROKER,call
from src.demo_assets import validate_training,validate_safety
from src.mpc import ProtocolError
ROOT=Path(__file__).resolve().parents[1]
FILES=('src/demo_page.py','src/demo_assets.py','ui/index.html','ui/app.js','ui/style.css','ui/common.js','ui/training.html','ui/training.js','ui/privacy.html','ui/privacy.js','ui/model-public.json','ui/training-public.json','ui/safety-public.json')
def check():
    differences=[]
    for name in FILES:
        target=CODE/name;source=ROOT/name
        if not target.is_file() or target.read_bytes()!=source.read_bytes():differences.append(name)
        elif target.stat().st_uid!=0 or target.stat().st_mode&0o222:raise RuntimeError('RUNTIME_PUBLIC_ASSET_NOT_ADMIN_READONLY')
    if differences:return dict(status='PENDING_ADMIN_DEPLOYMENT',runtime_commit=CODE.resolve().name,differing_public_files=differences,query_submitted=False,materials_generated=False)
    overview=call(BROKER,dict(action='overview'),timeout=3)
    if not overview['connected']:raise RuntimeError('UPDATED_REAL_UID_AUDIT_REQUIRED')
    def get(route):
        with urllib.request.urlopen('http://127.0.0.1:8765'+route,timeout=5) as response:return response.read()
    for path,title in (('/','隐私推理'),('/training','训练与效果'),('/privacy','隐私与运行保障')):
        text=get(path).decode();assert title in text and '__PUBLIC_' not in text and '__DISPLAY_CONTEXT__' not in text
    training=validate_training(json.loads(get('/training-public.json')));safety=validate_safety(json.loads(get('/safety-public.json')))
    assert training==json.loads((ROOT/'ui/training-public.json').read_text());assert safety==json.loads((ROOT/'ui/safety-public.json').read_text())
    return dict(status='PASS_DEPLOYED_PUBLIC_PAGES',runtime_commit=CODE.resolve().name,source_sha256=overview['source_sha256'],public_assets_readonly=True,pages=3,existing_permission_record_checks=sum(r['checks'] for r in safety['audit']['roles']),curve_points=len(training['actual']['loss_curve']),query_submitted=False,materials_generated=False,scope='Fixed real service GET and source-bound role attestation; browser rendering acceptance remains separately recorded')
def main():
    try:value=check()
    except (OSError,RuntimeError,AssertionError,ValueError,ProtocolError) as error:value=dict(status='DEPLOYMENT_DISPLAY_CHECK_FAILED',error_type=type(error).__name__,query_submitted=False,materials_generated=False)
    out=ROOT/'results/demo-final';out.mkdir(parents=True,exist_ok=True)
    (out/'deployment-display-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value));sys.exit(0 if value['status']=='PASS_DEPLOYED_PUBLIC_PAGES' else 2)
if __name__=='__main__':main()
