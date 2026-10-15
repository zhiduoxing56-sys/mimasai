"""Two real, fresh-material published-model requests through the loopback API.

Run only after administrator deployment and real-UID audit. This operator-side
verifier reads accepted public reference evidence, never role-private assets.
It stops after a failed request; invoking it again never repeats an old token.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.local_deployment import Client,query,require_deployment
from src.deployment import BROKER,CODE,call

ROOT=Path(__file__).resolve().parents[1]
EXPERIMENT='a49152b33097752eaf81a7cba6d910a3'
OUT=ROOT/'results/chapter5/full-query-acceptance.json'
SOURCE=ROOT/'results/application'/EXPERIMENT/'acceptance.json'
OLD_SESSION='7a4cda63efe0fc5b06c4a45aa9af3e32'
MODEL='829a29a6913d505e7167f418a94674ee'
TARGET='936'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def reference():
    doc=json.loads(SOURCE.read_text())
    assert doc['status']=='PASS_ACTUAL_TRAINED_MODEL_TARGET_ONLY_QUERIES' and doc['model_id']==MODEL
    assert doc['checkpoint_to_m12_to_m7_verified'] and doc['diagnostic_same_model_all_traces_bitwise']
    old=next(q for q in doc['queries'] if q.get('session')==OLD_SESSION)
    expected=old['result']['results'][0]['probability_units']
    assert old['result']['results'][0]['node_id']==TARGET and old['result']['model_id']==MODEL
    return doc,old,expected

def installed():
    revision=json.loads((CODE/'config/source-manifest.json').read_text())['commit']
    head=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert revision==head,'FROZEN_SOURCE_NOT_CURRENT'
    expected=json.loads((ROOT/'build/he_bridge-build.json').read_text())['binary_sha256']
    assert digest(Path('/opt/privacy-gnn/native/build/he_bridge'))==expected,'FROZEN_NATIVE_NOT_CURRENT'
    require_deployment(call(BROKER,dict(action='evidence'))['permissions'])
    return dict(commit=revision,native_sha256=expected)

def marker():return call(BROKER,dict(action='overview')).get('cached_state')

def baseline(old):
    stages=old['online']['servers'][0]['operations']
    return dict(source='既有完整双层 HE/FSS 真实验收',session=OLD_SESSION,
                online=dict(wall_seconds=old['online']['wall_seconds'],wire_bytes=old['online']['wire_bytes'],rounds=old['online']['rounds'],
                            stages=[dict(type=s['type'],operation=s['operation'],elapsed_seconds=s['elapsed_seconds'],
                                         wire_bytes=s['bytes_sent']+old['online']['servers'][1]['operations'][i]['bytes_sent'],rounds=s['rounds']) for i,s in enumerate(stages)]),
                offline_wall_seconds=old['offline']['offline_wall_seconds'],condition='优化前，无首层缓存；同一发布模型和64节点目标')

def assert_new(proof,expected,mode,cold=None):
    assert proof['state']=='cleaned' and proof['report'] is not None,'QUERY_NOT_COMPLETE'
    report=proof['report'];result=report['result'];online=report['online']
    assert report['plan_mode']==mode and report['source_iteration']==160 and report['model_id']==MODEL
    assert result['request_id']==proof['session'] and result['model_id']==MODEL and result['results'][0]['node_id']==TARGET
    actual=result['results'][0]['probabilities'];assert len(actual)==len(expected)
    assert all(abs(a-b/4096)<1e-12 for a,b in zip(actual,expected)),'FIXED_REFERENCE_MISMATCH'
    types=[s['type'] for s in online['stages']]
    if mode=='cold_full':
        assert types[:2]==['matmul','he_aggregate'] and types.count('he_aggregate')==2
        assert report['cache_source_session'] is None
    else:
        assert types[0]=='load_hidden' and types.count('he_aggregate')==1 and types.count('matmul')==1
        assert report['cache_source_session']==cold
    assert types[-2:]==['probability','deliver']
    assert sum(s['wire_bytes'] for s in online['stages'])<=online['wire_bytes']
    assert sum(s['rounds'] for s in online['stages'])<=online['rounds']
    assert proof['identifiers']['session']==proof['session'] and proof['identifiers']['batch']==proof['batch']
    return dict(condition=mode,session=proof['session'],batch=proof['batch'],model_id=MODEL,graph_binding='role-local input, model and HE asset hashes checked by hidden cache',
                cache_source_session=report['cache_source_session'],online=online,offline_wall_seconds=report['offline']['offline_wall_seconds'],
                total_request_wall_seconds=report.get('wall_seconds'),probability_units=expected,probabilities=actual,
                cleanup=report.get('retention'),reference_equal=True)

def distinct(a,b):
    x,y=a['identifiers'],b['identifiers']
    assert x['batch']!=y['batch'] and x['session']!=y['session']
    assert not set(x['ring_material_ids'])&set(y['ring_material_ids'])
    assert not {v for row in x['he_mask_ids'] for v in row}&{v for row in y['he_mask_ids'] for v in row}
    return dict(distinct_batches=True,ring_material_ids_disjoint=True,he_mask_ids_disjoint=True)

def save(doc):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    temp=OUT.with_suffix('.pending');temp.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');temp.replace(OUT)

def main():
    deployment=installed();accepted,old,expected=reference()
    if OUT.exists():
        doc=json.loads(OUT.read_text())
        assert doc['deployment']==deployment and doc['reference_sha256']==digest(SOURCE),'ACCEPTANCE_SOURCE_CHANGED'
        if doc['status']=='PASS_TWO_FULL_QUERIES':print(json.dumps(dict(status='ALREADY_COMPLETE',evidence=str(OUT))));return
        assert doc['status']=='COLD_COMPLETE','PREVIOUS_ATTEMPT_REQUIRES_REVIEW'
    else:
        assert marker() is None,'FIRST_REQUEST_WOULD_NOT_BE_COLD'
        doc=dict(status='STARTED',deployment=deployment,reference_sha256=digest(SOURCE),reference_method='已验收独立定点验证器 published_reference 与 verify_queries；本轮不读取双方秘密或恢复完整状态',
                 expected_probability_units=expected,baseline=baseline(old),requests=[])
        save(doc)
    client=Client();client.authorize()
    if not doc['requests']:
        cold=query(client);row=assert_new(cold,expected,'cold_full')
        cache=marker();assert cache and cache['source_session']==cold['session'],'FIRST_LAYER_CACHE_NOT_INSTALLED'
        doc['requests'].append(row);doc['cold_cache_binding']=cache['binding'];doc['status']='COLD_COMPLETE';save(doc)
    assert len(doc['requests'])==1
    warm=query(client);row=assert_new(warm,expected,'cache_hit',doc['requests'][0]['session'])
    cache=marker();assert cache and cache['binding']==doc['cold_cache_binding'] and cache['source_session']==doc['requests'][0]['session']
    cold_evidence=call(BROKER,dict(action='query_evidence',sid=doc['requests'][0]['session']))
    doc['fresh_material']=distinct(cold_evidence,warm)
    doc['requests'].append(row);doc['status']='PASS_TWO_FULL_QUERIES'
    base=doc['baseline']['online'];c=doc['requests'][0]['online'];w=row['online']
    doc['ratios']=dict(baseline_over_cold_wall=base['wall_seconds']/c['wall_seconds'],baseline_over_warm_wall=base['wall_seconds']/w['wall_seconds'],
                       cold_over_warm_wall=c['wall_seconds']/w['wall_seconds'],baseline_over_cold_wire=base['wire_bytes']/c['wire_bytes'],
                       baseline_over_warm_wire=base['wire_bytes']/w['wire_bytes'],cold_over_warm_wire=c['wire_bytes']/w['wire_bytes'])
    save(doc);print(json.dumps(dict(status=doc['status'],evidence=str(OUT),ratios=doc['ratios']),ensure_ascii=False))

if __name__=='__main__':main()
