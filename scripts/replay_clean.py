"""Check out committed source and restore only hash-locked public archives."""
import hashlib,json,secrets,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/reproducibility';OUT.mkdir(parents=True,exist_ok=True)
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
work=ROOT.parent/('privacy_gnn-replay-'+secrets.token_hex(6));started=time.monotonic()
subprocess.run(['git','worktree','add','--detach',str(work),commit],cwd=ROOT,check=True)
assert not (work/'build').exists() and not (work/'state').exists() and not (work/'deps').exists()
lock=json.loads((work/'config/dependencies.lock.json').read_text());required=[r for r in lock if r['file'].endswith('.deb') or r['file']=='SEAL-4.1.0.tar.gz'];missing=[r['file'] for r in required if not (ROOT/'deps/downloads'/r['file']).is_file()]
report=dict(commit=commit,worktree=str(work),historical_private_material_copied=False,missing_offline_runtime_archives=missing,system_prerequisites=['Linux amd64','/usr/bin/python3 >=3.12','Git','dpkg-deb'],all_dependencies_offline_rebuilt=False)
if missing:
 report['status']='BLOCKED_MISSING_OFFLINE_ARCHIVES';(OUT/'clean-replay.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit('Missing offline archives: '+', '.join(missing))
(work/'deps/downloads').mkdir(parents=True)
for row in required:
 source=ROOT/'deps/downloads'/row['file'];assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256'];shutil.copyfile(source,work/'deps/downloads'/row['file'])
(work/'results').mkdir()
for label,command in [('restore',[sys.executable,'scripts/unpack_deps.py']),('seal-build',['sh','scripts/build_he.sh']),('bridge-build',['sh','scripts/build_stage3.sh']),('replay',[sys.executable,'verification/replay_minimal.py'])]:
 with (OUT/(label+'.log')).open('w') as log:subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True)
replay=json.loads((work/'results/replay/summary.json').read_text());assert len(set(replay['sessions']))==len(replay['sessions']);report.update(status=replay['status'],replay=replay,locked_runtime_archives_restored=len(required),seal_rebuilt_from_locked_source=True,wall_seconds=time.monotonic()-started,ledger_retained=str(work/'state/mpc'))
(OUT/'clean-replay.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
