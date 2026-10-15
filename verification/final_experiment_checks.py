"""Short checks over retained Chapter 5 runs; never execute a protocol."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.storage import estimate

def read(path):return json.loads(path.read_text())

def main():
    raw=ROOT/'results/final-experiments'
    reports=[read(p) for p in raw.glob('*.json') if p.name.startswith(('he-','aggregation-','activation-'))
             and '.failed.' not in p.name and not p.name.endswith('-failure.json')]
    complete=[q for q in reports if q.get('status') in ('PASS_OUTPUT_BITWISE','PASS_EQUAL_TO_PLAINTEXT')]
    assert len(complete)>=12
    ids=[q['session'] for q in complete]
    assert len(ids)==len(set(ids)), 'fresh session IDs must be unique'
    head=ROOT/'results/chapter5/summary.json'
    summary=read(head)
    assert summary['groups']['1_training']['nodes']==64
    assert summary['groups']['2_publication']['checkpoint_binding_verified']
    assert len(summary['groups']['3_aggregation'])==8
    assert {r['average_degree'] for r in summary['groups']['3_aggregation']}=={2,4,8,16}
    assert {r['comparison_width_bits'] for r in summary['groups']['4_activation']}=={10,32}
    tested=[]
    for result in summary['groups']['4_activation']:
        sid=result['session'];base=ROOT/'build/final-experiments/runtime/build/stage2'/sid
        jobs=[read(base/f'S{role}/input.json')['operations'][0]['x'] for role in (0,1)]
        values=[((a+b)%(1<<32)) for a,b in zip(*jobs)]
        tested.append([v if v<1<<31 else v-(1<<32) for v in values])
    assert tested[0]==tested[1] and all(-512<=v<512 for v in tested[0])
    assert summary['groups']['5_inference']['external_baseline']=='UNMEASURED_SAME_WORKLOAD'
    assert summary['goals']['external_20x_latency']=='MISSING_COMPARABLE_BASELINE'
    assert {100,200,500,1000}<={r['nodes'] for r in summary['groups']['6_scale']}
    traced=next(r for r in complete if r.get('conversion')=='private_decryption' and
                r.get('nodes')==64 and r.get('columns')==6 and r.get('trace_ciphertexts'))
    compact=next(r for r in complete if r.get('conversion')=='private_decryption' and
                 r.get('nodes')==64 and r.get('columns')==6 and not r.get('trace_ciphertexts'))
    runtime=ROOT/'build/final-experiments/runtime/build/stage3'
    assert len(list((runtime/traced['session']).glob('S*/trace/*.ct')))==2*6*(2*64+1)
    assert not list((runtime/compact['session']).glob('S*/trace/*.ct'))
    public={'shape':[64,6],'degree':8192,'data_moduli':[1,3,5]}
    old=dict(type='he_aggregate',conversion='legacy_ciphertext',
             he={key:value for key,value in public.items() if key!='data_moduli'})
    secure=dict(old,conversion='private_decryption')
    assert estimate([old],{})['native_trace_bytes']>0
    assert estimate([dict(old,trace_ciphertexts=False)],{})['native_trace_bytes']==0
    assert estimate([secure],{})['native_work_bytes']>0
    assert estimate([dict(secure,trace_ciphertexts=False)],{})['native_trace_bytes']==0
    for image in ('训练损失.svg','节点度与聚合时间.svg','单层聚合规模.svg'):
        root=ET.parse(ROOT/'results/chapter5'/image).getroot()
        assert root.tag=='{http://www.w3.org/2000/svg}svg'
    print(json.dumps(dict(status='PASS_RETAINED_FINAL_EXPERIMENT_CHECKS',
        unique_sessions=len(ids),four_degree_points=True,comparison_widths=True,
        trace_files_removed_from_new_mode=True,legacy_disk_budget_restored=True,
        external_targets_not_falsely_claimed=True),ensure_ascii=False))

if __name__=='__main__':main()
