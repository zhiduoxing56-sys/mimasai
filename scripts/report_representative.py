"""Summarize authorized aggregate results without reading private shares/materials."""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def aggregate(value):
 if isinstance(value,dict):return {k:aggregate(v) for k,v in value.items() if k not in ('nodes','probabilities','range_audits','servers','message_trace','preprocessing','configuration')}
 if isinstance(value,list):return [aggregate(v) for v in value]
 return value

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment');a=p.parse_args();directory=ROOT/'results/representative';read=lambda name:json.loads((directory/name).read_text());frozen=read('frozen.json');old=read('old-checkpoints.json');fixed=read('fixed.json');float_results=read('float.json');rep=read('replication.json');numeric=read('numeric.json');prec=read('precision.json');result=dict(frozen=frozen,old_checkpoints=aggregate(old),primary_fixed=[dict(seed=r['seed'],curves=aggregate(r['curves']),first_protocol_guard_violation=r['first_protocol_guard_violation']) for r in fixed['results']],primary_float_effects=aggregate(float_results['effects']),replication=aggregate(rep),numeric=numeric,precision=dict(status=prec['status'],minimum_exponential_units=prec['minimum_exponential_units'],seven_class_minimum_probability_units=prec['seven_class_minimum_probability_units'],log_max_absolute_error=prec['log_max_absolute_error'],actual_secret_log_samples=prec['runs'][1]['checks'],all_positive_integer_reference_count=prec['log_all_positive_integer_reference_count']),scope='Authorized public benchmark aggregate evaluation; no private parameters or full per-node probabilities. Reference320 weight guard violation is not secure training.')
 training_path=directory/'shared-training/reference.json'
 if training_path.exists():
  training=json.loads(training_path.read_text());steps=training.get('secure_training',[]);result['actual_training']=dict(status=training['status'],steps=len(steps),budget=160,dimensions=training['dimensions'],checkpoint=training.get('checkpoint'),online_bytes=sum(s['wire_bytes'] for s in steps),rounds=sum(s['rounds'] for s in steps),online_seconds=sum(s['seconds'] for s in steps),offline_seconds=sum(s['dealer']['offline_wall_seconds'] for s in steps),first_loss=steps[0]['loss'] if steps else None,last_preupdate_loss=steps[-1]['loss'] if steps else None,loss_curve=[dict(iteration=s['iteration'],preupdate_loss=s['loss']) for s in steps])
  with (directory/'learning-curve.csv').open('w',newline='') as file:
   writer=csv.writer(file);writer.writerow(['update','reference_float_loss','reference_fixed_loss','float_train_accuracy','fixed_train_accuracy','float_validation_accuracy','fixed_validation_accuracy','actual_shared_preupdate_loss'])
   for q in training['curves']:i=q['iteration'];writer.writerow([i,q['float_loss'],q['fixed_loss'],q['float_train_accuracy'],q['fixed_train_accuracy'],q['float_validation_accuracy'],q['fixed_validation_accuracy'],steps[i]['loss'] if i<len(steps) else ''])
  metrics=directory/'actual-checkpoints.json'
  if metrics.exists():result['actual_checkpoint_metrics']=aggregate(json.loads(metrics.read_text()))
 if a.experiment:
  app=ROOT/'results/application'/a.experiment;acceptance=json.loads((app/'acceptance.json').read_text());pipeline=json.loads((app/'pipeline.json').read_text());result['actual_application']=dict(experiment_id=a.experiment,status=acceptance['status'],pipeline_status=pipeline['status'],training_steps=acceptance['training_steps'],model_id=acceptance['model_id'],same_model_all_paths_bitwise=acceptance['diagnostic_same_model_all_traces_bitwise'],effects=acceptance['effects'],costs=acceptance['costs'],probability_max_error=acceptance['probability_max_error'],classification_equal=acceptance['classification_equal_high_precision'],query_count=len(pipeline['requests']),faults=[dict(fault=q['fault'],no_output=q.get('no_output'),restart=q.get('restart')) for q in acceptance['queries'] if 'fault' in q]);result['application_cost_summary']=json.loads((app/'summary.json').read_text())
 for key,name in [('log_high_precision','log-high-precision.json'),('log_boundary_checks','log-boundaries.json'),('sampling_overlap','sampling-overlap.json'),('environment_interruption','interruption.json')]:
  extra=directory/name
  if extra.exists():result[key]=aggregate(json.loads(extra.read_text()))
 clean=ROOT/'results/reproducibility/representative-clean-replay.json'
 if clean.exists():result['clean_replay']=json.loads(clean.read_text())
 (directory/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(ROOT/'docs/representative-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.get('actual_training',{}).items() if k!='loss_curve'},indent=2))
if __name__=='__main__':main()
