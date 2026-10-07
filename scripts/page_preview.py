"""Three disconnected, self-contained review pages; no backend or example query."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];UI=ROOT/'ui';OUT=ROOT/'results/demo-final/static-review';OUT.mkdir(parents=True,exist_ok=True)
values={'__PUBLIC_MODEL__':json.loads((UI/'model-public.json').read_text()),'__PUBLIC_TRAINING__':json.loads((UI/'training-public.json').read_text()),'__PUBLIC_SAFETY__':json.loads((UI/'safety-public.json').read_text()),'__DISPLAY_CONTEXT__':dict(mode='pending_deployment')}
for page,script in (('index','app.js'),('training','training.js'),('privacy','privacy.js')):
    html=(UI/(page+'.html')).read_text()
    for marker,value in values.items():html=html.replace(marker,json.dumps(value,ensure_ascii=False).replace('<','\\u003c'))
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(UI/'style.css').read_text()+'</style>')
    for name in ('common.js',script):html=html.replace('<script src="/'+name+'"></script>','<script>'+(UI/name).read_text()+'</script>')
    html=html.replace('href="/training"','href="training.html"').replace('href="/privacy"','href="privacy.html"').replace('href="/"','href="index.html"')
    (OUT/(page+'.html')).write_text(html)
print(str(OUT/'index.html'))
