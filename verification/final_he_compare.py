"""Isolated, fresh-material comparison of the two existing HE converters.

This is a performance/correctness experiment. The legacy ciphertext route
retains its documented ciphertext-view security limitation.
"""
import argparse
import copy
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SOURCE_ROOT = Path(__file__).resolve().parents[1]
ISOLATED_ROOT = SOURCE_ROOT / 'build/final-experiments/runtime'
# The installed service owns state/mpc and state/storage. Benchmark sessions
# have a separate root, native binary, state databases and one-shot materials.
for name in ('build', 'results', 'state'):
    (ISOLATED_ROOT / name).mkdir(parents=True, exist_ok=True)
for target, source in ((ISOLATED_ROOT / 'config', SOURCE_ROOT / 'config'),
                       (ISOLATED_ROOT / 'deps', SOURCE_ROOT / 'deps'),
                       (ISOLATED_ROOT / 'build/he_bridge', SOURCE_ROOT / 'build/he_bridge'),
                       (ISOLATED_ROOT / 'results/stage1', SOURCE_ROOT / 'results/stage1')):
    if not target.exists():
        target.symlink_to(source, target_is_directory=source.is_dir())
os.environ['PGNN_ROOT'] = str(ISOLATED_ROOT)
os.environ['PGNN_GATE_DIR'] = str(ISOLATED_ROOT / 'state/storage')
os.environ['PYTHONPATH'] = str(SOURCE_ROOT) + os.pathsep + os.environ.get('PYTHONPATH', '')
from src.he import native
from src.mpc import VERSION, private_write
from src.reference import Fixed
from src.storage import snapshot, policy
from verification.stage2 import launch
from verification.stage3 import C, MOD, ROOT, bundle

OUT = SOURCE_ROOT / 'results/final-experiments'


def run(conversion, nodes=5, columns=1, trace=True, average_degree=None):
    if conversion not in ('legacy_ciphertext', 'private_decryption'):
        raise ValueError('unknown conversion')
    if not 1 <= nodes <= 1000 or not 1 <= columns <= C['model_reference']['hidden_width']:
        raise ValueError('single-layer experiment scope exceeded')
    space = snapshot(ROOT)
    if space['host_status'] != 'READABLE':
        raise RuntimeError('HOST_SPACE_UNKNOWN: no fresh material generated')
    # HE setup happens before offline admission. Reserve its pair of encrypted
    # graph-row bundles as well as the ordinary runtime safety margin.
    setup_bound = 2 * nodes * (C['he_execution_degree'] * 3 * 2 * 8 + 65536)
    cfg = policy()
    if (space['internal_available_bytes'] < setup_bound + cfg['internal_reserve_bytes'] or
            space['host_available_bytes'] < setup_bound + cfg['host_reserve_bytes']):
        raise RuntimeError('SETUP_DISK_BUDGET_REJECTED')
    d, sid, public, setup, propagation, transform, _ = bundle(nodes, average_degree)
    public['shape'] = [nodes, columns]
    public['column_order'] = [f'column-{j}' for j in range(columns)]
    if conversion == 'private_decryption':
        public['data_moduli'] = native(['metadata', d / 'S0'])['data_moduli']
        os.link(d / 'S0/parameters.seal', d / 'parameters.seal')
    for role in (0, 1):
        own = d / f'S{role}'
        manifest = json.loads((own / 'he.json').read_text())
        manifest['public'] = public
        (own / 'he.json').write_text(json.dumps(manifest))
    fraction = C['fraction_bits']
    op = dict(type='he_aggregate', conversion=conversion, count=nodes * columns,
              fraction=fraction, activation='none', he=public, trace_ciphertexts=trace)
    private_write(d / 'public-plan.json', dict(session=sid, bits=C['ring_bits'], plan=[op]))
    started = time.perf_counter()
    dealer = subprocess.run([sys.executable, '-m', 'src.offline', str(d), str(d / 'public-plan.json')],
                            cwd=ROOT, capture_output=True, text=True)
    if dealer.returncode:
        raise RuntimeError('offline failed before inputs: ' + dealer.stderr[-800:])
    offline_seconds = time.perf_counter() - started
    offline = json.loads(dealer.stdout)
    values = [transform[row][col] for row in range(nodes) for col in range(columns)]
    first = [secrets.randbits(32) for _ in values]
    shares = [first, [(v - a) % MOD for v, a in zip(values, first)]]
    for role in (0, 1):
        job = copy.deepcopy(op)
        job['x'] = shares[role]
        private_write(d / f'S{role}/input.json', dict(version=VERSION, session=sid,
                      role=role, bits=C['ring_bits'], operations=[job]))
    started = time.perf_counter()
    attempt, metrics = launch(d, sid, C['ring_bits'], timeout=240)
    wall_seconds = time.perf_counter() - started
    if not all(m['success'] for m in metrics):
        raise RuntimeError(f'actual protocol failed: {[m["error"] for m in metrics]}')
    outputs = [json.loads((d / f'S{role}' / f'output-{attempt}.json').read_text())['shares'][0]
               for role in (0, 1)]
    recovered = [(a + b) % MOD for a, b in zip(*outputs)]
    fixed = Fixed(C)
    raw = [sum(fixed.signed(propagation[row][j]) * fixed.signed(transform[j][col])
               for j in range(nodes)) % MOD for row in range(nodes) for col in range(columns)]
    expected = raw + [fixed.signed(v) // (1 << fraction) % MOD for v in raw]
    if recovered != expected:
        raise AssertionError('HE output differs from same-condition fixed-point oracle')
    if not all(m['preprocessing']['consumed'] == offline['generated'] for m in metrics):
        raise AssertionError('offline consumption mismatch')
    ops = [m['operations'][0] for m in metrics]
    profiles = [next(c['he_profile'] for c in o['components'] if 'he_profile' in c) for o in ops]
    return dict(status='PASS_OUTPUT_BITWISE', conversion=conversion, nodes=nodes,
                trace_ciphertexts=trace, average_degree=average_degree,
                scope='one HE aggregation layer with synthetic graph/input; no model or full inference' if nodes>64 else 'one HE aggregation layer',
                columns=columns, session=sid, setup_seconds=setup['wall_seconds'],
                offline_seconds=offline_seconds, offline_generated=offline['generated'],
                online_wall_seconds=wall_seconds,
                online_wire_bytes=sum(m['communication']['bytes_sent'] for m in metrics),
                online_rounds=metrics[0]['communication']['exchange_rounds'],
                aggregation_wire_bytes=sum(o['bytes_sent'] for o in ops),
                aggregation_rounds=ops[0]['rounds'],
                aggregation_worker_seconds=max(o['elapsed_seconds'] for o in ops),
                native_eval_seconds=max(p['elapsed_seconds'] for p in profiles),
                native_multiply_seconds=max(p['multiply_seconds'] for p in profiles),
                native_extract_seconds=max(p['extract_trace_seconds'] for p in profiles),
                native_pack_seconds=max(p['pack_seconds'] for p in profiles),
                conversion_seconds=max(p['conversion_seconds'] for p in profiles),
                native_profiles=profiles, online_components=[o['components'] for o in ops],
                security_condition=('legacy masked-ciphertext exchange, ciphertext-view limitation'
                                    if conversion == 'legacy_ciphertext'
                                    else 'private-input protected BFV decryption, trusted offline'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--conversion', choices=['legacy_ciphertext', 'private_decryption', 'both'], default='both')
    parser.add_argument('--nodes', type=int, default=5)
    parser.add_argument('--columns', type=int, default=1)
    parser.add_argument('--no-trace', action='store_true')
    parser.add_argument('--degree', type=int, choices=[2,4,8,16])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    routes = (['legacy_ciphertext', 'private_decryption'] if args.conversion == 'both'
              else [args.conversion])
    for route in routes:
        try:
            report = run(route, args.nodes, args.columns, not args.no_trace, args.degree)
        except BaseException as error:
            failure = dict(status='FAILED', route=route, nodes=args.nodes, columns=args.columns,
                           error_type=type(error).__name__, error=str(error))
            (OUT / f'he-{route}-{args.nodes}x{args.columns}-d{args.degree if args.degree else "default"}-{"no-trace" if args.no_trace else "trace"}-{secrets.token_hex(4)}-failure.json').write_text(
                json.dumps(failure, indent=2) + '\n')
            raise
        path = OUT / f'he-{route}-{args.nodes}x{args.columns}-d{args.degree if args.degree else "default"}-{"no-trace" if args.no_trace else "trace"}-{report["session"]}.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({k: report[k] for k in ('status', 'conversion', 'nodes', 'columns',
              'online_wall_seconds', 'online_wire_bytes', 'online_rounds',
              'native_eval_seconds', 'conversion_seconds')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
