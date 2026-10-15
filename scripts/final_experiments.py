"""Unified Chapter 5 dispatcher. Each protocol attempt uses a fresh session."""
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.storage import snapshot

RAW=ROOT/'results/final-experiments'

def command(name,*args):
    cmd=[sys.executable,str(ROOT/name),*map(str,args)]
    done=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    return dict(command=[Path(cmd[1]).relative_to(ROOT).as_posix(),*cmd[2:]],
                returncode=done.returncode,stdout=done.stdout[-4000:],stderr=done.stderr[-4000:])

def present(glob):
    return any(p.is_file() and '.failed.' not in p.name and not p.name.endswith('-failure.json')
               for p in RAW.glob(glob))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--group',choices=['all','1','2','3','4','5','6'],default='all')
    p.add_argument('--dataset',default='Cora')
    p.add_argument('--nodes',type=int,default=64)
    p.add_argument('--repeat',type=int,default=1)
    p.add_argument('--scale-nodes',nargs='+',type=int,default=[100,200,500,1000])
    p.add_argument('--execute',action='store_true',help='run only missing short protocol experiments')
    p.add_argument('--force-new-sessions',action='store_true',help='explicitly repeat successful experiments with fresh material')
    a=p.parse_args()
    if a.dataset!='Cora':p.error('只有 Cora 已连接真实数据、标签和已发布模型')
    if a.nodes!=64:p.error('当前已发布模型和度数对照绑定 64 节点；扩展实验用 --scale-nodes')
    if not 1<=a.repeat<=5:p.error('repeat 范围为 1..5')
    if any(n not in (100,200,500,1000) for n in a.scale_nodes):p.error('可用的单层容量档位为100/200/500/1000')
    RAW.mkdir(parents=True,exist_ok=True)
    groups=['1','2','3','4','5','6'] if a.group=='all' else [a.group]
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    diff=subprocess.check_output(['git','diff','--binary'],cwd=ROOT)
    config=(ROOT/'config/phase0.json').read_bytes()
    cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
              if line.startswith('model name')),platform.processor())
    report=dict(kind='CHAPTER5_DISPATCH',id=secrets.token_hex(8),
        started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),source_commit=commit,
        working_diff_sha256=hashlib.sha256(diff).hexdigest(),
        config_sha256=hashlib.sha256(config).hexdigest(),
        environment=dict(python=sys.version.split()[0],platform=platform.platform(),cpu=cpu,
                         os_cpu_count=os.cpu_count(),space_before=snapshot(ROOT)),
        request=dict(group=a.group,dataset=a.dataset,nodes=a.nodes,repeat=a.repeat,
                     scale_nodes=a.scale_nodes,execute=a.execute,force_new_sessions=a.force_new_sessions),
        groups={},commands=[])
    report['source_artifact_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('src/he.py','src/he_bridge.cpp','src/he_secure.py','src/offline.py',
                     'src/storage.py','verification/final_he_compare.py',
                     'verification/final_aggregate.py','verification/final_activation.py',
                     'scripts/report_chapter5.py')}
    path=RAW/f'dispatch-{report["id"]}.json'
    def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    save()
    def run(name,*args):
        outcome=command(name,*args);report['commands'].append(outcome);save()
        if outcome['returncode']:
            raise RuntimeError(f'{name} failed: {outcome["stderr"][-500:]}')
    for group in groups:
        try:
            if group in ('1','2','5'):
                report['groups'][group]='REUSED_ACCEPTED_RECORDS; NO_NEW_PROTOCOL'
            elif not a.execute:
                report['groups'][group]='RENDER_ONLY_NO_PROTOCOL'
            elif group=='3':
                for repetition in range(a.repeat):
                    for degree in (2,4,8,16):
                        for route in ('he','shared'):
                            glob=f'aggregation-{route}-n64-c1-d{degree}*.json'
                            if repetition==0 and not a.force_new_sessions and present(glob):continue
                            run('verification/final_aggregate.py','--nodes',64,'--columns',1,
                                '--degrees',degree,'--route',route)
                report['groups'][group]='MEASURED_OR_REUSED_4_DEGREES'
            elif group=='4':
                if a.force_new_sessions or not all(present(f'activation-k{k}-n32*.json') for k in (10,32)):
                    for _ in range(a.repeat):
                        run('verification/final_activation.py','--count',32,'--widths',10,32)
                report['groups'][group]='MEASURED_OR_REUSED_SAME_INPUT_10_32'
            else:
                for repetition in range(a.repeat):
                    for nodes in a.scale_nodes:
                        glob=f'he-private_decryption-{nodes}x1-ddefault-no-trace*.json'
                        if repetition==0 and not a.force_new_sessions and present(glob):continue
                        run('verification/final_he_compare.py','--conversion','private_decryption',
                            '--nodes',nodes,'--columns',1,'--no-trace')
                report['groups'][group]='SINGLE_LAYER_SYNTHETIC_CAPACITY_ONLY'
        except BaseException as error:
            report['groups'][group]=dict(status='FAILED',reason=str(error));save()
            continue
        save()
    render=command('scripts/report_chapter5.py')
    report['commands'].append(render)
    report['render_status']='PASS' if render['returncode']==0 else 'FAILED'
    report['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    report['environment']['space_after']=snapshot(ROOT)
    save()
    print(json.dumps(dict(id=report['id'],groups=report['groups'],render_status=report['render_status'],
        record=str(path)),ensure_ascii=False,indent=2))
    return 0 if render['returncode']==0 and not any(isinstance(v,dict) for v in report['groups'].values()) else 2

if __name__=='__main__':raise SystemExit(main())
