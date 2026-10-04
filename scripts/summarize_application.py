"""Summarize public acceptance/cost reports; never open private runtime files."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiment');a=p.parse_args()
    if len(a.experiment)!=32 or any(v not in '0123456789abcdef' for v in a.experiment):raise ValueError('EXPERIMENT_ID')
    out=ROOT/'results/application'/a.experiment
    acceptance=json.loads((out/'acceptance.json').read_text())
    queries=[];names=('linear0','aggregate_activation0','linear1','aggregate1','probability_scale','probability','delivery')
    for q in acceptance['queries']:
        if 'fault' in q:continue
        online=q['online'];servers=online['servers'];phases=[]
        for i,name in enumerate(names):
            operations=[s['operations'][i] for s in servers]
            assert operations[0]['rounds']==operations[1]['rounds']
            phases.append(dict(name=name,bytes_sent=sum(op['bytes_sent'] for op in operations),rounds=operations[0]['rounds'],max_role_seconds=max(op['elapsed_seconds'] for op in operations)))
        he_details=[dict(layer=layer,roles=[[v['he_profile'] for v in s['operations'][index]['components'] if 'he_profile' in v] for s in servers]) for layer,index in ((0,1),(1,3))] if q['route']=='he' else []
        queries.append(dict(he_details=he_details,request=q['session'],route=q['route'],activation=q['activation'],online_bytes=online['wire_bytes'],online_rounds=online['rounds'],online_wall_seconds=online['wall_seconds'],offline_seconds=q['offline']['offline_wall_seconds'],offline_materials=q['offline']['generated'],offline_peak_rss_kib=q['offline']['peak_rss_kib'],role_peak_rss_kib=[s['peak_rss_kib'] for s in servers],phases=phases,handshake_bytes=online['wire_bytes']-sum(o['bytes_sent'] for o in phases),handshake_rounds=online['rounds']-sum(o['rounds'] for o in phases),target_result=q['result'],recipient_export_bytes=q['export_bytes']))
    r=dict(status=acceptance['status'],experiment=a.experiment,dimensions=acceptance['dimensions'],training_steps=acceptance['training_steps'],model_id=acceptance['model_id'],checkpoint_binding_verified=acceptance['checkpoint_to_m12_to_m7_verified'],all_diagnostic_states_bitwise=acceptance['diagnostic_same_model_all_traces_bitwise'],effects=acceptance['effects'],probability_max_error=acceptance['probability_max_error'],costs={k:v for k,v in acceptance['costs'].items() if k not in ('publication_online','publication_offline')},publication=dict(role_peak_rss_kib=[s['peak_rss_kib'] for s in acceptance['costs']['publication_online']['servers']],online={k:v for k,v in acceptance['costs']['publication_online'].items() if k!='servers'},offline=acceptance['costs']['publication_offline']),queries=queries,faults=[q for q in acceptance['queries'] if 'fault' in q],counting='Phases partition online totals; handshake separate; nested HE/rounding components are NOT added again. Offline preparation and exports separate. RSS cumulative per-process highwater, not phase allocation. Full validation recovery is independent of recipient.')
    (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],experiment=a.experiment,summary=str(out/'summary.json'),dimensions=r['dimensions'],training_steps=r['training_steps'],model_id=r['model_id'],all_diagnostic_states_bitwise=r['all_diagnostic_states_bitwise'],probability_max_error=r['probability_max_error'],queries=[{k:q[k] for k in ('request','route','activation','online_bytes','online_rounds','online_wall_seconds','offline_seconds')} for q in queries]),indent=2))
if __name__=='__main__':main()
