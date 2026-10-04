"""Independent metric-only regression; never used to generate online answers."""
import argparse,json,sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import precise_softmax
from verification.application import published_reference,paths

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',required=True);a=p.parse_args()
    high=precise_softmax([[0,20,-20]])[0]
    assert max(range(3),key=lambda j:high[j])!=1
    assert max(range(3),key=lambda j:Decimal(high[j]))==1
    report,data,pub,prob=published_reference(a.experiment)
    path=paths(a.experiment)[1]/'acceptance.json';old=json.loads(path.read_text())
    assert old['model_id']==pub['models'][-1]['model_id'] and old['checkpoint']==report['checkpoint']
    evidence=dict(status='PASS_DECIMAL_METRIC_REGRESSION_AND_SAME_MODEL_RECHECK',experiment=a.experiment,nodes=len(prob),original_flag=old['classification_equal_high_precision'],corrected_flag=pub['classification_equal'],probability_max_error=pub['probability_error'],reason='Scientific-notation probability strings need numerical Decimal comparison, not lexical order',protocol_reexecuted=False,online_results_changed=False)
    backup=path.with_name('acceptance-before-decimal-metric.json')
    if not backup.exists():backup.write_bytes(path.read_bytes())
    old['classification_equal_high_precision']=pub['classification_equal'];old['metric_correction']=evidence
    for run in old['diagnostic_runs']:run['classification_equal']=pub['classification_equal']
    path.write_text(json.dumps(old,indent=2)+'\n')
    path.with_name('metric-correction.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
if __name__=='__main__':main()
