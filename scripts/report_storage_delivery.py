"""Aggregate public evaluation/cost evidence without reading private shares."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import ROOT,config
from src.data import cora
from src.sparse_reference import sparse,step
from src.metrics import evaluate

def metric(m):
 return {k:v for k,v in m.items() if k in ('count','accuracy','macro_precision','macro_recall','macro_f1','classes','missing_true_classes','macro_policy','confusion')}
def effects(rows):return [dict(seed=r['seed'],metrics={split:metric(m) for split,m in r['metrics'].items()}) for r in rows]
def main():
 out=ROOT/'results/representative';read=lambda name:json.loads((out/name).read_text());word=read('feature-control.json');fixed=read('fixed.json');frozen=read('frozen.json');floats=read('float.json');d=cora(node_count=64,sampling=frozen['sampling'],seed=frozen['sampling_seed']);mask=[i in d['splits']['train'] for i in range(64)];gcn=[]
 for seed in config()['data_experiment']['representative']['seeds']:
  weights=json.loads((ROOT/f'build/representative/h{frozen["hidden"]}-lr{frozen["learning_rate"]}-seed{seed}.json').read_text())['160'];tr,_,_=step(sparse(d['propagation']),sparse(d['features']),weights,d['labels'],mask,learning_rate=frozen['learning_rate']);gcn.append(dict(seed=seed,metrics=evaluate(d,tr['probabilities'])))
 label_free=[]
 for r in word['label_free_existing_reference']:
  curves=[dict(mode=q['mode'],iteration=q['iteration'],metrics={s:metric(m) for s,m in q['metrics'].items()}) for q in r['curves'] if 'metrics' in q and q['iteration'] in (160,320)]
  label_free.append(dict(strategy=r['strategy'],sampling_seed=r['sampling_seed'],topology=r['topology'],curves=curves))
 demo=json.loads((ROOT/'results/storage/demo-checks.json').read_text());checks=json.loads((ROOT/'results/storage/checks.json').read_text());training=json.loads((ROOT/'results/storage/training-checks.json').read_text())
 result=dict(scope='Existing data/seed/split; word-only control and same-checkpoint small reference ablations. No shared training rerun, node expansion, primitive re-proof or full-state online recovery.',
  frozen_gcn=frozen,word_selection=word['selection'],label_names=word['label_names'],word_validation_selected=effects(word['effects']),word_matched_160=effects(word['matched_160']),gcn_float_existing_160=effects(gcn),gcn_float_existing_validation_selected=effects(floats['effects']),primary_gcn_fixed_160={s:metric(m) for s,m in next(q for q in fixed['results'][0]['curves'] if q['iteration']==160)['metrics'].items()},
  label_free_existing_reference=label_free,numerical=read('numeric-attribution.json'),storage_checks=checks,training_stop_checks=training,demo=demo,post_hoc_control=True,no_test_driven_resampling=True,numerical_protocol_modified=False,historical_cleanup_executed=False,os_role_isolation_implemented=False,retained_query_checks=json.loads((ROOT/'results/storage/retained-query-checks.json').read_text()))
 (ROOT/'docs/storage-delivery-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(word_selection=word['selection'],gcn_float_160_tests=[r['metrics']['test']['accuracy'] for r in gcn]),indent=2))
if __name__=='__main__':main()
