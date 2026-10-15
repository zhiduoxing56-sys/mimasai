"""Package only allowlisted public Chapter 5 measurements and screenshot."""
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
files=[ROOT/'docs'/name for name in ('chapter5-results.md','chapter5-runbook.md','chapter5-status.json','performance-engineering.md','full-inference-acceptance.md','full-inference-results.md','full-inference-capacity.md')]
files += sorted((ROOT/'public/chapter5').iterdir())
files += [ROOT/'results/local-page/connected-success.png']
forbidden={'shares','materials','secret_key','private_key','password','token','input_shares','ledger'}
def check(value,path):
    if isinstance(value,dict):
        if forbidden & value.keys():raise RuntimeError('private field in '+str(path))
        for item in value.values():check(item,path)
    elif isinstance(value,list):
        for item in value:check(item,path)
for path in sorted((ROOT/'results/final-experiments').glob('*.json')):
    if not path.name.startswith(('aggregation-','activation-','he-')):continue
    if '.failed.' in path.name or path.name.endswith('-failure.json'):continue
    record=json.loads(path.read_text())
    if record.get('status') not in ('PASS_OUTPUT_BITWISE','PASS_EQUAL_TO_PLAINTEXT'):continue
    check(record,path);files.append(path)
for name,status in (
    ('bitpacked-channel.json','PASS_BITPACKED_WIRE'),
    ('fused-range.json','PASS_FUSED_SECRET_RANGE'),
    ('hidden-cache-reuse.json','PASS_FRESH_SESSION_HIDDEN_REUSE'),
    ('probability-prefix-64.json','PASS_EXACT_PROBABILITY_PREFIX')):
    path=ROOT/'results/final-experiments'/name
    record=json.loads(path.read_text())
    if record.get('status')!=status:raise RuntimeError('Unexpected optimization evidence status: '+name)
    check(record,path);files.append(path)
rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,
           sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
manifest=dict(kind='PUBLIC_CHAPTER5_EVIDENCE',source_commit=subprocess.check_output(
    ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=rows,
    limitations='No private model, input share, key, one-time material, ledger, or full verifier trace')
archive=OUT/'chapter5-evidence.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for row in rows:tar.add(ROOT/row['path'],arcname=row['path'],recursive=False)
    import io
    encoded=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    info=tarfile.TarInfo('chapter5-manifest.json');info.size=len(encoded);info.mode=0o644
    tar.addfile(info,io.BytesIO(encoded))
(OUT/'chapter5-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(archive=str(archive),files=len(files),bytes=archive.stat().st_size,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest()),ensure_ascii=False))
