"""Public-shape-only 1000-node admission estimate; never executes a protocol."""
import copy,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.application import inference_plan
from src.mpc import costs
from src.storage import estimate,snapshot

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/application/a49152b33097752eaf81a7cba6d910a3/manifest.json'
OUTPUT=ROOT/'public/chapter5/full-capacity-plan.json'

def main():
    report=json.loads(SOURCE.read_text());assert report['dimensions']==[64,551,6,7]
    assert report['publication']['models'][-1]['model_id']=='829a29a6913d505e7167f418a94674ee'
    target=1000;copy_report=copy.deepcopy(report);copy_report['dimensions'][0]=target
    # Artificial IDs are used only to count shape-dependent material. They are
    # never sent to a role, written to its assets, or accepted as a real graph.
    order=list(report['data']['node_order'])+[f'estimate-only-{i}' for i in range(target-64)]
    for model in copy_report['publication']['models']:model['node_order']=order
    copy_report['he_setup']['public']['node_order']=order
    copy_report['he_setup']['public']['shape'][0]=target
    full=inference_plan(copy_report,'he','fss',report['allowed_targets'])
    cached=dict(binding=full[1]['cache_binding'],source_session='0'*32)
    plans={'full':full,'cache_hit':inference_plan(copy_report,'he','fss',report['allowed_targets'],cached)}
    estimates={name:dict(operations=[op['type'] for op in plan],counts=(count:=costs(plan,32)),admission=estimate(plan,count)) for name,plan in plans.items()}
    memory=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    current=snapshot(ROOT)
    accepted=json.loads((ROOT/'results/chapter5/full-query-acceptance.json').read_text())
    assert accepted['status']=='PASS_TWO_FULL_QUERIES'
    out=dict(status='PUBLIC_SHAPE_ESTIMATE_ONLY',nodes=target,source_model_id=report['publication']['models'][-1]['model_id'],
             source_iteration=report['publication']['source_training_iteration'],source_runtime_commit=accepted['deployment']['commit'],
             he_degree=report['he_setup']['public']['degree'],ring_bits=32,plans=estimates,
             capacity=dict(physical_memory_bytes=memory,internal_available_bytes=current['internal_available_bytes'],
                           host_available_bytes=current['host_available_bytes'],host_status=current['host_status']),
             interpretation='Only existing public count and disk estimator with synthetic node IDs; no real graph, keys, materials, model rebinding, range verification, or 1000-node inference.')
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=out['status'],full_budget=estimates['full']['admission']['total_bytes'],cached_budget=estimates['cache_hit']['admission']['total_bytes']),ensure_ascii=False))

if __name__=='__main__':main()
