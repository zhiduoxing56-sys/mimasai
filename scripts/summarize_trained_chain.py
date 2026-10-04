"""Read public run metrics only; never inspect private keys/shares/ledgers."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];source=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT;out=ROOT/'results/trained-he';out.mkdir(parents=True,exist_ok=True)
rows=[]
def collect(label,report):
 for i,a in enumerate(report['servers'][0]['operations']):
  b=report['servers'][1]['operations'][i]
  rows.append(dict(stage=label,operation=i,type=a['type'],wire_bytes=a['bytes_sent']+b['bytes_sent'],rounds=a['rounds'],max_party_seconds=max(a['elapsed_seconds'],b['elapsed_seconds']),consumed_per_party=a['consumed'],party_highwater_rss_kib=[a.get('process_highwater_rss_kib'),b.get('process_highwater_rss_kib')],components_by_party=[a.get('components',[]),b.get('components',[])]))
train=json.loads((source/'results/continuation/training-indexed.json').read_text());publication=json.loads((source/'results/continuation/publication-indexed.json').read_text());collect('training',train);collect('publication_and_shared_probability',publication)
for route in ('shared','he'):
 for activation in ('boolean','fss'):collect(route+'-'+activation,json.loads((source/f'results/trained-he/{route}-{activation}.json').read_text()))
report=dict(scope='Public online metrics only; child components nested, not additive; highwater RSS cumulative, not independent operator peaks',source_root=str(source),source_training_session=train['session'],publication_session=publication['session'],rows=rows)
(out/'complete-costs.json').write_text(json.dumps(report,indent=2)+'\n');print('Wrote complete costs:',len(rows),'operations')
