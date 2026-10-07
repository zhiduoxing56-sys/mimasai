"""Package explicitly selected public evidence; never scan private state."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'review'
NAMES=(
 'results/local-page/real-uid-permissions.json',
 'results/local-page/migration-evidence.json',
 'results/local-page/diagnostic-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/admin-diagnostic-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/public-mode-before-fix.json',
 'results/local-page/public-mode-after-fix.json',
 'results/local-page/deployment-mode-tests.json',
 'results/local-page/old-deployment-refusal.json',
 'results/local-page/reuse-c3c435f768cd4c6c9a0ef99421dc96eb.json',
 'results/local-page/current-space-observation.json',
 'results/local-page/diagnostic-short-tests.json',
 'results/local-page/short-tests.json',
 'results/local-page/installer-recovery-tests.json',
 'results/local-page/browser-ready-evidence.json',
 'results/local-page/connected-ready.png',
 'results/local-page/disconnected.png',
 'docs/local-deployment-progress.json',
)

def main():
 OUT.mkdir(exist_ok=True);files=[]
 for name in NAMES:
  path=ROOT/name
  if not path.is_file() or path.is_symlink():raise RuntimeError('Missing/nonregular public evidence: '+name)
  files.append(dict(path=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 manifest=dict(scope='Selected public evidence only; connected idle screenshot is not a successful query. No credentials, cookies, browser profile or role-private files.',files=files)
 with tarfile.open(OUT/'local-page-evidence.tar.gz','w:gz') as archive:
  for row in files:archive.add(ROOT/row['path'],arcname=row['path'],recursive=False)
  data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('public-evidence-manifest.json');info.size=len(data)
  import io
  archive.addfile(info,io.BytesIO(data))
 print(json.dumps(dict(files=len(files),bytes=(OUT/'local-page-evidence.tar.gz').stat().st_size,path=str(OUT/'local-page-evidence.tar.gz'))))
if __name__=='__main__':main()
