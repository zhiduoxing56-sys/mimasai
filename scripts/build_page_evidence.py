"""Package explicitly selected public evidence; never scan private state."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'review'
NAMES=(
 'results/local-page/real-uid-permissions.json',
 'results/local-page/real-uid-permissions-a761ba5b7e034e52b21efbeafc6569e19520189c1bcf6c6d06122b7f488c6dfb.json',
 'results/local-page/migration-evidence.json',
 'results/local-page/migration-evidence-1c8f376416c7a07d18749d9f77f69e282ac9d339.json',
 'results/local-page/diagnostic-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/diagnostic-public-modes-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/admin-diagnostic-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/public-mode-before-fix.json',
 'results/local-page/public-mode-after-fix.json',
 'results/local-page/deployment-mode-tests.json',
 'results/local-page/old-deployment-refusal.json',
 'results/local-page/reuse-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/current-space-observation.json',
 'results/local-page/final-space-observation.json',
 'results/local-page/diagnostic-short-tests.json',
 'results/local-page/short-tests.json',
 'results/local-page/installer-recovery-tests.json',
 'results/local-page/browser-ready-evidence.json',
 'results/local-page/connected-ready.png',
 'results/local-page/disconnected.png',
 'results/local-page/query-success.json',
 'results/local-page/query-failure.json',
 'results/local-page/request-independence.json',
 'results/local-page/real-page-api-boundary.json',
 'results/local-page/real-services.json',
 'results/local-page/browser-evidence.json',
 'results/local-page/connected-success.png',
 'results/local-page/connected-failure.png',
 'docs/local-deployment-progress.json',
 'results/local-page/real-uid-permissions-cf7da5b3c1929bbc299a7ad1a688035d4ba88643e453fed8b43add54dd972509.json',
 'docs/representative-results.json',
 'docs/storage-delivery-results.json',
 'docs/demo-public-assets.json',
 'docs/demo-final-results.json',
 'docs/demo-final-acceptance.md',
 'docs/demo-runbook.md',
 'ui/model-public.json',
 'ui/training-public.json',
 'ui/safety-public.json',
 'results/demo-final/scope-and-space.json',
 'results/demo-final/display-short-tests.json',
 'results/demo-final/browser-display-evidence.json',
 'results/demo-final/deployment-display-check.json',
 'results/demo-final/test-server-stop.json',
 'results/demo-final/inference-pending.png',
 'results/demo-final/training-pending.png',
 'results/demo-final/privacy-pending.png',
 'results/demo-final/inference-acceptance-pending.png',
 'results/demo-final/failure-acceptance-pending.png',
 'results/demo-final/static-review/index.html',
 'results/demo-final/static-review/training.html',
 'results/demo-final/static-review/privacy.html',
)

def main():
 OUT.mkdir(exist_ok=True);files=[]
 for name in NAMES:
  path=ROOT/name
  if not path.is_file() or path.is_symlink():raise RuntimeError('Missing/nonregular public evidence: '+name)
  files.append(dict(path=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 manifest=dict(scope='Selected public evidence: retained e7e5436 real UID matrix, deployed loopback API query and input fault; NEW three-page Chinese display uses independent pending-deployment preview and retained-record HTTP adapter, no new cryptographic queries. New screenshots/static HTML are explicitly pending administrator deployment and are not page-UID acceptance. Public training metrics/curve and strict offline asset audit, short checks, space snapshots and runbook included. No credentials, cookies, browser profile or role-private files.',files=files)
 with tarfile.open(OUT/'local-page-evidence.tar.gz','w:gz') as archive:
  for row in files:archive.add(ROOT/row['path'],arcname=row['path'],recursive=False)
  data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('public-evidence-manifest.json');info.size=len(data)
  import io
  archive.addfile(info,io.BytesIO(data))
 print(json.dumps(dict(files=len(files),bytes=(OUT/'local-page-evidence.tar.gz').stat().st_size,path=str(OUT/'local-page-evidence.tar.gz'))))
if __name__=='__main__':main()
