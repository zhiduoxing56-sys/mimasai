"""Aggregate measured public results; never supply recovered values to a server."""
import csv
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import ROOT
from verification.real_data import accuracy

OUT = ROOT / 'results/real-data'

def read(name, directory=OUT):
    return json.loads((directory / name).read_text())

def material_sum(items):
    counts = Counter()
    for item in items:
        counts.update(item)
    return dict(counts)

def totals(steps):
    return dict(
        successful_steps=len(steps),
        wire_bytes=sum(s['wire_bytes'] for s in steps),
        rounds=sum(s['rounds'] for s in steps),
        launch_wall_seconds=sum(s['seconds'] for s in steps),
        offline_wall_seconds=sum(s['dealer']['offline_wall_seconds'] for s in steps),
        preprocessing=material_sum(s['dealer']['generated'] for s in steps),
        role_peak_rss_kib=[max(s['servers'][role]['peak_rss_kib'] for s in steps) for role in (0, 1)],
    )

def main():
    train = read('reference.json')
    chain = read('chain.json')
    publication = read('publication.json')
    clean = read('real-data-clean-replay.json', ROOT / 'results/reproducibility')
    assert train['secure_steps'] == chain['training_steps'] == 96
    assert chain['training_checkpoint'] == train['checkpoint']
    assert publication['source_training_session'] == Path(train['checkpoint']['directory']).name
    assert publication['source_training_iteration'] == 96
    assert clean['status'] == 'PASS_CLEAN_CORA_SHARED_TRAINING_TO_PROTECTED_HE_PROBABILITY'
    assert clean['historical_private_material_copied'] is False
    fresh = Path(clean['worktree']) / 'results/real-data'
    full = read('full-reference.json', fresh)
    clean_train = read('reference.json', fresh)
    clean_chain = read('chain.json', fresh)
    assert full['float_test_accuracy'] > full['majority_test_accuracy']
    assert full['fixed_failure']['iteration'] == 72
    assert clean_chain['training_steps'] == clean_train['secure_steps'] == 16
    data = cora()
    inference = []
    first = None
    for activation in ('boolean', 'fss'):
        for route in ('shared', 'he'):
            result = read(f'{route}-{activation}.json')
            assert result['source_training_session'] == publication['source_training_session']
            assert result['model'] == publication['models'][-1]
            traces = result['restored_verifier_traces']
            if first is None:
                first = traces
            assert traces == first
            assert all(all(p.startswith(f'S{m["role"]}/') for p in m['loaded_private_files']) for m in result['servers'])
            inference.append(dict(
                route=route, activation=activation, wire_bytes=result['wire_bytes'],
                rounds=result['rounds'], launch_wall_seconds=result['wall_seconds'],
                offline_wall_seconds=result['offline_seconds'],
                preprocessing=result['offline']['generated'],
                role_peak_rss_kib=[m['peak_rss_kib'] for m in result['servers']],
                he_setup=result['he_setup'], he_oracle=result['he_oracle'],
                # Operation totals do not double count nested BFV-round components.
                operations=[dict(index=i, type=op['type'],
                    wire_bytes=sum(m['operations'][i]['bytes_sent'] for m in result['servers']),
                    rounds=op['rounds'], worker_seconds=max(m['operations'][i]['elapsed_seconds'] for m in result['servers']),
                    components=op['components'])
                    for i, op in enumerate(result['servers'][0]['operations'])],
            ))
    count, classes = train['dimensions'][0], train['dimensions'][-1]
    probabilities = [first[-1][i * classes:(i + 1) * classes] for i in range(count)]
    metrics = {name: accuracy(probabilities, data['labels'], indices) for name, indices in data['splits'].items()}
    majority = Counter(data['labels'][i] for i in data['splits']['train']).most_common(1)[0][0]
    majority_test = sum(data['labels'][i] == majority for i in data['splits']['test']) / len(data['splits']['test'])
    publish_ops = publication['servers'][0]['operations'][:2]
    publishing = dict(
        wire_bytes=sum(m['operations'][i]['bytes_sent'] for m in publication['servers'] for i in (0, 1)),
        rounds=sum(op['rounds'] for op in publish_ops),
        worker_seconds=sum(max(m['operations'][i]['elapsed_seconds'] for m in publication['servers']) for i in (0, 1)),
        preprocessing=material_sum(op['consumed'] for op in publish_ops),
        full_publication_session_with_mpc_validation_wire_bytes=publication['wire_bytes'],
        full_publication_session_with_mpc_validation_rounds=publication['rounds'],
        extra_session_hello_bytes=publication['wire_bytes'] - sum(m['operations'][i]['bytes_sent'] for m in publication['servers'] for i in range(len(m['operations']))),
    )
    scale32 = read('reference.json', ROOT / 'results/real-data-32')
    failures = read('state8-failure.json')
    result = dict(
        status='PASS_REAL_CORA16_SHARED_TRAIN_PUBLISH_PROTECTED_HE_PROBABILITY_WITH_FULL_GRAPH_LIMITS',
        checkpoint=train['checkpoint'], model_ids=[m['model_id'] for m in publication['models']],
        dimensions=train['dimensions'], verified_trace_groups=6, values_per_inference=sum(map(len, first)),
        same_model_all_four_variants_bitwise=True,
        shared_training=totals(train['secure_training']),
        failed_state8_attempt=dict(iteration=91, errors=[m['error'] for m in failures['servers']],
            wire_bytes=sum(m['communication']['bytes_sent'] for m in failures['servers']),
            rounds=failures['servers'][0]['communication']['exchange_rounds'],
            reserved_burned=failures['servers'][0]['preprocessing']['reserved'],
            offline_seconds=None, reason='Failed attempt offline time was not retained; not fabricated'),
        published_model_accuracy=metrics, subgraph_majority_test_accuracy=majority_test,
        training_comparison_at_model96=train['curves'][96],
        publishing=publishing, inference=inference,
        probability_max_error_same_f7_model=publication['probability_error'],
        probability_sum_range=[min(publication['probability_sums']), max(publication['probability_sums'])],
        probability_classification_equal_high_precision=publication['classification_equal'],
        full_graph_plaintext=dict(dimensions=full['dimensions'], iterations=len(full['curve']),
            selected_iteration=full['float_validation_selected_iteration'],
            validation_accuracy=full['float_validation_selected_accuracy'],
            test_accuracy=full['float_test_accuracy'], majority_test_accuracy=full['majority_test_accuracy'],
            initial_loss=full['curve'][0]['float_loss'], final_loss=full['curve'][-1]['float_loss'],
            fixed_failure=full['fixed_failure'], operand_policy_violation=full['first_protocol_operand_policy_violation'],
            maximum_probability_error_before_fixed_block=max(row.get('probability_max_error', 0) for row in full['curve']),
            reference_seconds=full['seconds'], peak_rss_kib=full['peak_rss_kib']),
        scale32=dict(dimensions=scale32['dimensions'], training=totals(scale32['secure_training']),
            last_loss=scale32['secure_training'][-1]['loss'], scope='Two verified updates only; no secure learning-quality or HE32 closure claim'),
        clean_replay=dict(commit=clean['commit'], worktree=clean['worktree'], secure_steps=16,
            source_pipeline_wall_seconds=clean['wall_seconds'], training=totals(clean_train['secure_training']),
            reference_status=full['status'], ledger_retained=clean['ledger_retained']),
        failures=chain['faults'], ledger_audit=read('ledger-audit.json'),
        download=read('download-check.json'), budget=read('scale-budget.json'),
        counting='Sum both-direction socketpair sent bytes including headers; rounds count one paired exchange; setup/file transfer/oracle/build excluded from online totals; operation subtotals exclude hello; nested components are not added again; RSS is cumulative process highwater, not per-operation or total physical memory',
        limits=['Public benchmark with reproducible initialization is not an unknown private-data deployment',
            'Cora16 induced graph differs from original full graph; normalization is plaintext owner preparation',
            'Approximate standard p-y gradients; no derivative-equivalence claim',
            'Trusted noncolluding offline, passive local processes; no authentication or active security',
            'Legacy ciphertext conversion remains blocked; private decryption is not original low-interaction protocol',
            'Full graph fixed training: domain/range/frame/streaming limits; f14 probability is only a numeric candidate',
            'Clean replay uses 16 updates, not a repeated 96-update effect experiment'],
    )
    (OUT / 'acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    for name, curve in [('subgraph-curves.csv', train['curves']), ('full-graph-curves.csv', full['curve'])]:
        fields = sorted({key for row in curve for key in row})
        with (OUT / name).open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(curve)
    print(json.dumps({key: result[key] for key in ('status', 'dimensions', 'published_model_accuracy', 'same_model_all_four_variants_bitwise', 'probability_max_error_same_f7_model')}, indent=2))

if __name__ == '__main__':
    main()
