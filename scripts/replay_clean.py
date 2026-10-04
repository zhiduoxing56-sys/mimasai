"""Check out committed source and restore only hash-locked public archives."""
import argparse,hashlib,json,secrets,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/reproducibility';OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group();mode.add_argument('--real-data',action='store_true');mode.add_argument('--application',action='store_true');parser.add_argument('--nodes',type=int,choices=(16,32,64),default=16);parser.add_argument('--secure-steps',type=int,default=16);parser.add_argument('--sampling',choices=('fixed_bfs','uniform','multi_start','stratified_frontier'),default='fixed_bfs');parser.add_argument('--sampling-seed',type=int,default=20261005);args=parser.parse_args()
report_file=OUT/(('representative-clean-replay.json' if args.sampling!='fixed_bfs' else 'application-clean-replay.json') if args.application else 'real-data-clean-replay.json' if args.real_data else 'clean-replay.json')
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
work=ROOT.parent/('privacy_gnn-replay-'+secrets.token_hex(6));started=time.monotonic()
subprocess.run(['git','worktree','add','--detach',str(work),commit],cwd=ROOT,check=True)
assert not (work/'build').exists() and not (work/'state').exists() and not (work/'deps').exists()
lock=json.loads((work/'config/dependencies.lock.json').read_text());required=[r for r in lock if r['file'].endswith('.deb') or r['file']=='SEAL-4.1.0.tar.gz'];missing=[r['file'] for r in required if not (ROOT/'deps/downloads'/r['file']).is_file()]
report=dict(commit=commit,worktree=str(work),historical_private_material_copied=False,missing_offline_runtime_archives=missing,system_prerequisites=['Linux amd64','/usr/bin/python3 >=3.12','Git','dpkg-deb'],all_dependencies_offline_rebuilt=False)
if missing:
 report['status']='BLOCKED_MISSING_OFFLINE_ARCHIVES';report_file.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit('Missing offline archives: '+', '.join(missing))
(work/'deps/downloads').mkdir(parents=True)
for row in required:
 source=ROOT/'deps/downloads'/row['file'];assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256'];shutil.copyfile(source,work/'deps/downloads'/row['file'])
if args.real_data or args.application:
 data=json.loads((work/'config/phase0.json').read_text())['data_experiment'];source=ROOT/'deps/downloads/cora.tgz'
 if source.is_file():
  assert hashlib.sha256(source.read_bytes()).hexdigest()==data['sha256'];shutil.copyfile(source,work/'deps/downloads/cora.tgz');report['locked_public_data_archive_copied']=True
 else:report['locked_public_data_archive_copied']=False
 report['requested_secure_training_steps']=args.secure_steps
(work/'results').mkdir()
for label,command in [('restore',[sys.executable,'scripts/unpack_deps.py']),('seal-build',['sh','scripts/build_he.sh']),('bridge-build',['sh','scripts/build_stage3.sh']),('replay',[sys.executable,'scripts/run_application.py','--nodes',str(args.nodes),'--steps',str(args.secure_steps),'--sampling',args.sampling,'--seed',str(args.sampling_seed),'--validate','--faults'] if args.application else [sys.executable,'verification/replay_real_data.py','--secure-steps',str(args.secure_steps)] if args.real_data else [sys.executable,'verification/replay_minimal.py'])]:
 try:
  with (OUT/(work.name+'-'+label+'.log' if args.application else label+'.log')).open('w') as log:subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True)
 except subprocess.CalledProcessError as error:
  report.update(status='FAILED_CLEAN_REPLAY',failed_step=label,exit_code=error.returncode,ledger_retained=str(work/'state/mpc'))
  report_file.write_text(json.dumps(report,indent=2)+'\n')
  (OUT/('failure-'+work.name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
  raise
if args.application:
 candidates=list((work/'results/application').glob('*/pipeline.json'));assert len(candidates)==1
 pipeline=json.loads(candidates[0].read_text());acceptance=json.loads(candidates[0].with_name('acceptance.json').read_text());manifest=json.loads(candidates[0].with_name('manifest.json').read_text());training=json.loads(Path(manifest['training_report']).read_text());replay=dict(status='PASS_CLEAN_REAL_APPLICATION_TARGET_ONLY_QUERIES',experiment_id=pipeline['experiment_id'],dimensions=acceptance['dimensions'],secure_steps=acceptance['training_steps'],sessions=[s['session'] for s in training['secure_training']]+[manifest['publication']['session']]+pipeline['requests'],same_model_four_diagnostic_paths_bitwise=acceptance['diagnostic_same_model_all_traces_bitwise'],target_queries=len(pipeline['requests']),fresh_query_batches=len({q['offline']['batch'] for q in acceptance['queries'] if 'offline' in q}),faults=[q for q in acceptance['queries'] if 'fault' in q],scope='Fresh committed own source and public archives; independent final-only recipient, target authorization and query replay burn; limited round count')
else:replay=json.loads((work/'results/replay/summary.json').read_text())
assert len(set(replay['sessions']))==len(replay['sessions'])
report.update(status=replay['status'],replay=replay,locked_runtime_archives_restored=len(required),seal_rebuilt_from_locked_source=True,wall_seconds=time.monotonic()-started,ledger_retained=str(work/'state/mpc'))
report_file.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
