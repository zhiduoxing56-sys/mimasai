"""Allowlisted public summary from retained short optimization runs."""
import glob,json,os,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
READ=ROOT/'results/final-experiments'
OUT=ROOT/'public/chapter5/performance-engineering.json'


def load(path):return json.loads(Path(path).read_text())
def latest(pattern):
    for name in sorted(glob.glob(str(READ/pattern)),key=os.path.getmtime,reverse=True):
        if load(name).get('status')=='PASS_OUTPUT_BITWISE':return Path(name)
    raise RuntimeError('No successful retained HE comparison')


def main():
    old=load(READ/'he-private_decryption-64x6-no-trace.json')
    candidate=latest('he-private_decryption-64x6-ddefault-no-trace-*.json');new=load(candidate)
    assert old['status']==new['status']=='PASS_OUTPUT_BITWISE' and old['nodes']==new['nodes']==64 and old['columns']==new['columns']==6
    assert new['native_profiles'][0]['extraction_workers']==4 and new['native_profiles'][0]['extract_trace_includes_multiply']
    candidates=[item for path in glob.glob(str(READ/'he-private_decryption-64x6-ddefault-no-trace-*.json'))
                if (item:=load(path)).get('status')=='PASS_OUTPUT_BITWISE']
    parallel_only=next((item for item in candidates if item['online_wire_bytes']==old['online_wire_bytes'] and item['native_profiles'][0].get('extraction_workers')==4),None)
    grouped_only=next((item for item in candidates if new['online_wire_bytes']<item['online_wire_bytes']<old['online_wire_bytes']),None)
    app=load(ROOT/'results/application/a49152b33097752eaf81a7cba6d910a3/summary.json')
    previous=next(q for q in app['queries'] if q['route']=='he' and q['activation']=='fss')
    probability_old=next(stage for stage in previous['phases'] if stage['name']=='probability')
    probability_new=load(READ/'probability-prefix-64.json')
    assert probability_new['status']=='PASS_EXACT_PROBABILITY_PREFIX' and probability_new['rows']==64 and probability_new['classes']==7
    cache=load(READ/'hidden-cache-reuse.json');fused=load(READ/'fused-range.json');wire=load(READ/'bitpacked-channel.json')
    assert cache['status']=='PASS_FRESH_SESSION_HIDDEN_REUSE' and cache['changed_source_rejected']
    assert fused['status']=='PASS_FUSED_SECRET_RANGE' and fused['invalid_range_rejected']
    assert wire['status']=='PASS_BITPACKED_WIRE' and wire['padding_rejected']
    from src.application import inference_plan
    from src.mpc import costs
    from src.storage import estimate
    retained=load(ROOT/'results/application/a49152b33097752eaf81a7cba6d910a3/manifest.json')
    full_plan=inference_plan(retained,'he','fss',retained['allowed_targets'])
    cached_plan=inference_plan(retained,'he','fss',retained['allowed_targets'],
                               dict(binding=full_plan[1]['cache_binding'],source_session='0'*32))
    full_budget=estimate(full_plan,costs(full_plan,32))['total_bytes']
    cached_budget=estimate(cached_plan,costs(cached_plan,32))['total_bytes']
    result=dict(status='PASS_ISOLATED_ENGINEERING_CHECKS_NOT_DEPLOYED_FULL_QUERY',
                he_one_layer=dict(scope='64 nodes × 6 columns; private-decryption BFV conversion; fresh synthetic session; exact fixed-point output',
                                  baseline=dict(wall_seconds=old['online_wall_seconds'],wire_bytes=old['online_wire_bytes'],rounds=old['online_rounds'],native_eval_seconds=old['native_eval_seconds']),
                                  optimized=dict(wall_seconds=new['online_wall_seconds'],wire_bytes=new['online_wire_bytes'],rounds=new['online_rounds'],native_eval_seconds=new['native_eval_seconds'],extraction_workers=4),
                                  intermediate=dict(parallel_only=dict(wall_seconds=parallel_only['online_wall_seconds'],wire_bytes=parallel_only['online_wire_bytes'],rounds=parallel_only['online_rounds']) if parallel_only else None,
                                                    grouped_before_bitpacking=dict(wall_seconds=grouped_only['online_wall_seconds'],wire_bytes=grouped_only['online_wire_bytes'],rounds=grouped_only['online_rounds']) if grouped_only else None),
                                  measured_wall_speedup=old['online_wall_seconds']/new['online_wall_seconds'],
                                  measured_wire_reduction=old['online_wire_bytes']/new['online_wire_bytes'],
                                  comparison='Independent sessions on same host; wall time subject to host load'),
                probability=dict(scope='64 rows × 7 classes, f12, same fixed-shape circuit; old published-model query versus optimized synthetic inputs',
                                 baseline=dict(rounds=probability_old['rounds'],wire_bytes=probability_old['bytes_sent'],operation_seconds=probability_old['max_role_seconds']),
                                 optimized=dict(rounds=probability_new['actual_rounds'],wire_bytes=probability_new['actual_wire_bytes'],operation_seconds=probability_new['actual_operation_seconds'],values_checked=probability_new['fixed_point_outputs_checked']),
                                 exact_reference=True,comparability='Circuit cost comparable by public shape; not a new complete published-model query'),
                hidden_cache=dict(scope='7 nodes × 6 hidden coordinates, isolated HE/FSS first layer only',
                                  first_rounds=cache['first_layer_rounds'],reused_load_rounds=cache['reused_rounds'],
                                  first_wire_bytes=cache['first_layer_online_bytes'],reused_load_wire_bytes=cache['reused_online_bytes'],
                                  exact_values=cache['exact_values'],changed_source_rejected=True,
                                  installed_service_query_verified=False),
                range_fusion=dict(scope='5 secret values, signed floor f7 with k-bit range',
                                  baseline_rounds=fused['old_rounds'],optimized_rounds=fused['fused_rounds'],
                                  baseline_wire_bytes=fused['old_wire_bytes'],optimized_wire_bytes=fused['fused_wire_bytes'],
                                  invalid_range_rejected=True),
                bit_wire=dict(format='bitpacked-lsb0-v1',padding_rejected=True),
                admission_budget=dict(full_plan_bytes=full_budget,cached_plan_bytes=cached_budget,
                                      interpretation='Conservative admission estimates, not measured disk use or recovered space'),
                external_baseline=dict(latency_20x='NO_COMPARABLE_BASELINE',communication_400x='NO_COMPARABLE_BASELINE'),
                deployed_status='SOURCE_ONLY_REQUIRES_ADMIN_RELEASE_AND_REAL_UID_REAUDIT')
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],path=str(OUT),he_speedup=result['he_one_layer']['measured_wall_speedup'],he_wire_reduction=result['he_one_layer']['measured_wire_reduction'],probability_rounds=[probability_old['rounds'],probability_new['actual_rounds']]),ensure_ascii=False))


if __name__=='__main__':main()
