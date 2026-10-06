"""Archive only tracked, self-authored review sources; never scan private state."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
allowed=('src/','verification/','scripts/','docs/','config/','ui/')
rows=[]
for name in paths:
 if not name or not (name.startswith(allowed) or name in ('README.md','.gitignore')):continue
 p=ROOT/name
 if p.is_symlink() or not p.is_file():raise RuntimeError('Only regular own-source files accepted: '+name)
 if p.suffix not in ('.py','.cpp','.md','.json','.sh','.html','.css','.js') and name!='.gitignore':raise RuntimeError('Unexpected source extension: '+name)
 rows.append(dict(path=name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
manifest=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),scope='Tracked own source, public config, synthetic fixtures, protocol docs; no third-party code or private runtime artifacts',files=rows)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(OUT/'privacy-gnn-source-review.tar.gz','w:gz') as tar:
 for row in rows:tar.add(ROOT/row['path'],arcname=row['path'],recursive=False)
 tar.add(OUT/'manifest.json',arcname='review-manifest.json')
print(json.dumps(dict(files=len(rows),bytes=(OUT/'privacy-gnn-source-review.tar.gz').stat().st_size,path=str(OUT/'privacy-gnn-source-review.tar.gz')),indent=2))
