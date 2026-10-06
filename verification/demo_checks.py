"""Verify new requests independently using metadata and final-only results."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT
from src.storage import record

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',default='a49152b33097752eaf81a7cba6d910a3');a=p.parse_args();out=ROOT/'results/application'/a.experiment;manifest=json.loads((out/'manifest.json').read_text());reports=sorted(out.glob('demo-*.json'),key=lambda f:f.stat().st_mtime)[-2:];assert len(reports)==2
 runs=[json.loads(f.read_text()) for f in reports];identifiers=[]
 for r in runs:
  sid=r['request'];request=json.loads((out/f'request-{sid}.json').read_text());d=Path(request['directory']);ids=json.loads((d/'material-identifiers.json').read_text());identifiers.append(ids)
  assert r['model_id']==manifest['publication']['models'][-1]['model_id'] and r['source_iteration']==160
  assert r['full_state_recovered'] is False and record(sid)['state']=='cleaned'
  assert not any((d/f'S{i}/preprocessing.json').exists() or (d/f'S{i}/input.json').exists() for i in (0,1))
  assert not any(list((d/f'S{i}/he-layer{layer}/trace').glob('*.ct')) for i in (0,1) for layer in (0,1))
  assert r['result']['receiver_id']==manifest['receiver_id']
  assert [row['node_id'] for row in r['result']['results']]==manifest['allowed_targets']
  assert all(m['success'] and not m['error'] for m in request['online']['servers'])
  for role,m in enumerate(request['online']['servers']):
   assert all(not name.startswith(f'S{1-role}/') and not name.startswith('V/') for name in m['loaded_private_files'])
  assert len(ids['ring_material_ids'])==26 and all(len(v)==13 for v in ids['he_mask_ids'])
 assert len({r['request'] for r in runs})==2 and len({r['offline']['batch'] for r in runs})==2
 assert set(identifiers[0]['ring_material_ids']).isdisjoint(identifiers[1]['ring_material_ids'])
 assert set(sum(identifiers[0]['he_mask_ids'],[])).isdisjoint(sum(identifiers[1]['he_mask_ids'],[]))
 assert runs[0]['result']['results']==runs[1]['result']['results']
 report=dict(status='PASS_NEW_REQUEST_INDEPENDENT_MATERIALS_REAL_BACKEND_FINAL_ONLY',experiment=a.experiment,model_id=runs[0]['model_id'],source_iteration=160,requests=[r['request'] for r in runs],independent_batch_ring_and_mask_ids=True,receiver_results_identical=True,full_state_recovered=False,automatic_cleanup=True,costs=[dict(request=r['request'],offline_seconds=r['offline']['offline_wall_seconds'],online_seconds=r['online']['wall_seconds'],wire_bytes=r['online']['wire_bytes'],rounds=r['online']['rounds'],wall_seconds=r['wall_seconds'],dealer_peak_rss_kib=r['offline']['peak_rss_kib'],disk_budget_at_run=r['offline']['disk_budget'],current_disk_budget=r.get('current_disk_budget',r['offline']['disk_budget']),retention=r['retention']) for r in runs])
 target=ROOT/'results/storage/demo-checks.json';target.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
