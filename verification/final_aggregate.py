"""Same fixed-point P*T on encrypted-row HE and secret-shared dense baseline."""
import argparse
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.final_he_compare import OUT, ROOT, C, MOD, run as he_run
from verification.stage3 import fixture
from verification.stage2 import launch
from src.mpc import VERSION, private_write
from src.ranges import operand
from src.reference import Fixed
from src.storage import snapshot


def shared_run(nodes, columns, degree):
    space = snapshot(ROOT)
    if space['host_status'] != 'READABLE':
        raise RuntimeError('HOST_SPACE_UNKNOWN')
    p, transform, _, _ = fixture(nodes, degree)
    sid = secrets.token_hex(16)
    directory = ROOT / 'build/final-aggregate' / sid
    for role in (0, 1):
        (directory / f'S{role}').mkdir(parents=True, mode=0o700)
    fraction = C['fraction_bits']
    op = dict(type='shared_aggregate', dims=[nodes, nodes, columns], count=nodes*columns,
              fraction=fraction, bounds=[operand('propagation', fraction),
                                         operand('state', fraction)], activation='none')
    private_write(directory / 'public-plan.json', dict(session=sid, bits=32, plan=[op]))
    started = time.perf_counter()
    dealer = subprocess.run([sys.executable, '-m', 'src.offline', str(directory),
                             str(directory / 'public-plan.json')], cwd=ROOT,
                            capture_output=True, text=True)
    if dealer.returncode:
        raise RuntimeError('offline failed: ' + dealer.stderr[-800:])
    offline_seconds = time.perf_counter() - started
    offline = json.loads(dealer.stdout)
    x = [transform[row][col] for row in range(nodes) for col in range(columns)]
    pp = [v for row in p for v in row]
    x0 = [secrets.randbits(32) for _ in x]
    p0 = [secrets.randbits(32) for _ in pp]
    for role in (0, 1):
        job = dict(op, x=x0 if role == 0 else [(v-a)%MOD for v,a in zip(x,x0)],
                   p=p0 if role == 0 else [(v-a)%MOD for v,a in zip(pp,p0)])
        private_write(directory / f'S{role}/input.json',
                      dict(version=VERSION, session=sid, role=role, bits=32, operations=[job]))
    started = time.perf_counter()
    attempt, metrics = launch(directory, sid, 32, timeout=240)
    wall_seconds = time.perf_counter()-started
    if not all(m['success'] for m in metrics):
        raise RuntimeError(f'actual shared aggregation failed: {[m["error"] for m in metrics]}')
    values = [json.loads((directory / f'S{role}' / f'output-{attempt}.json').read_text())['shares'][0]
              for role in (0,1)]
    restored = [(a+b)%MOD for a,b in zip(*values)]
    fixed = Fixed(C)
    expected = [sum(fixed.signed(p[i][j])*fixed.signed(transform[j][col])
                    for j in range(nodes))//(1<<fraction)%MOD
                for i in range(nodes) for col in range(columns)]
    if restored != expected:
        raise AssertionError('shared P*T differs from fixed oracle')
    return dict(status='PASS_OUTPUT_BITWISE', route='shared_dense', nodes=nodes,
                columns=columns, average_degree=degree, session=sid,
                online_wall_seconds=wall_seconds,
                online_wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),
                online_rounds=metrics[0]['communication']['exchange_rounds'],
                aggregation_worker_seconds=max(m['operations'][0]['elapsed_seconds'] for m in metrics),
                offline_seconds=offline_seconds, offline_generated=offline['generated'],
                operation_count=nodes*nodes*columns,
                scope='Secret-shared dense matrix baseline; every P entry secret-shared')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--nodes', type=int, default=64)
    p.add_argument('--columns', type=int, default=1)
    p.add_argument('--degrees', type=int, nargs='+', default=[2,4,8,16])
    p.add_argument('--route', choices=['both','he','shared'], default='both')
    args = p.parse_args()
    if args.nodes != 64 or not 1 <= args.columns <= 6:
        raise ValueError('current degree experiment is restricted to 64 nodes, 1-6 columns')
    OUT.mkdir(parents=True,exist_ok=True)
    for degree in args.degrees:
        if degree not in (2,4,8,16):
            raise ValueError('unsupported degree')
        for route in (('he','shared') if args.route=='both' else (args.route,)):
            try:
                report = (he_run('private_decryption',args.nodes,args.columns,False,degree)
                          if route=='he' else shared_run(args.nodes,args.columns,degree))
                if route=='he':
                    report['route']='he_private_decryption'
                    report['operation_count']=args.nodes*args.columns
                path = OUT / f'aggregation-{route}-n{args.nodes}-c{args.columns}-d{degree}-{report["session"]}.json'
                path.write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps({k:report[k] for k in ('route','nodes','columns','average_degree',
                    'online_wall_seconds','online_wire_bytes','online_rounds','operation_count')},
                    ensure_ascii=False),flush=True)
            except BaseException as error:
                (OUT/f'aggregation-{route}-n{args.nodes}-c{args.columns}-d{degree}-{secrets.token_hex(4)}.failed.json').write_text(json.dumps(
                    dict(status='FAILED',route=route,degree=degree,error_type=type(error).__name__,
                         reason=str(error)),indent=2)+'\n')
                raise


if __name__ == '__main__':
    main()
