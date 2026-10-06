"""Build a disconnected, self-contained UI review from real public metadata."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];UI=ROOT/'ui';OUT=ROOT/'results/local-page';OUT.mkdir(parents=True,exist_ok=True)
html=(UI/'index.html').read_text().replace('__PUBLIC_MODEL__',json.dumps(json.loads((UI/'model-public.json').read_text()),ensure_ascii=False).replace('<','\\u003c'))
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(UI/'style.css').read_text()+'</style>')
html=html.replace('<script src="/app.js"></script>','<script>'+(UI/'app.js').read_text()+'</script>')
(OUT/'disconnected.html').write_text(html)
print(str(OUT/'disconnected.html'))
