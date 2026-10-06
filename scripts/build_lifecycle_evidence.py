"""Package public short-run evidence, never secret material or model values."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT
from src.storage import record,snapshot

def main():
    result=dict(baseline='c9840ed3cd373031d9f8e4dce55a87247e57cc02',timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Changed process groups/application lifecycle/retention only. No long training, no real page query, no original primitive rerun.',
        independent_runs={},report_sha256={})
    for name in ('process-checks','storage-checks','application-checks','role-preflight'):
        path=ROOT/f'results/lifecycle/{name}.json';raw=path.read_bytes()
        result['independent_runs'][name.replace('-','_')]=json.loads(raw)
        result['report_sha256'][name]=hashlib.sha256(raw).hexdigest()
    assert all(result['independent_runs'][name]['status'].startswith('PASS_CHANGED_') for name in ('process_checks','storage_checks','application_checks'))
    row=next(row for row in result['independent_runs']['application_checks']['cases'] if row['case']=='report_save')
    eid=Path(record(row['session'])['directory']).parents[1].name
    command=[sys.executable,'-m','src.application','status','--experiment',eid,'--request',row['session']]
    status=json.loads(subprocess.check_output(command,cwd=ROOT,text=True))
    assert status['delivery_state']=='incomplete' and status['failure_reason']=='IO_ERROR'
    assert not {'directory','batch','shares','servers'} & status.keys()
    result['status_cli_short_run']=dict(status=status,old_cache_is_not_delivery_evidence=True)
    result['privilege_probe_origin']='Captured actual tool results from this session; packaging does not rerun privileged commands.'
    result['privilege_probes']=[dict(command='sudo -n /usr/bin/id',execution='sandbox_permissions=require_escalated',exit_code=1,stderr='sudo: a password is required'),
        dict(command='sudo -n /usr/sbin/useradd --system --user-group --no-create-home --shell /usr/sbin/nologin pgnn-s0',execution='sandbox_permissions=require_escalated',exit_code=1,stderr='sudo: a password is required')]
    result['source_inspection']=dict(role_ledgers_written_by_role_helper=True,helper_uid_separation=False,
        cleanup_os_role_executor_implemented=False,model_restore_or_training_code_changed=False,
        numerical_semantics_or_range_guard_changed=False,process_group_scope='Honest same-group descendants, Linux /proc proof; no hostile setsid containment')
    result['existing_report_results']=dict(references=['docs/storage-delivery-results.json','docs/storage-delivery-acceptance.md','docs/representative-acceptance.md'],reexecuted=False,
        description='Existing 160-step model/classification/numerical/reference and query costs are prior evidence, not current short-run results.')
    result['space_at_package']=snapshot(ROOT)
    result['delivery']=dict(item_1='COMPLETED_SHORT_TESTS_PASS',item_2='BLOCKED_PRIVILEGED_ACCOUNT_CREATION',item_3='NOT_STARTED_PERMISSION_GATE_UNMET',actual_uid_permission_matrix='NOT_RUN',real_page_query_evidence='NOT_RUN',delivery_repair_supported=False)
    result['historical_acceptance']=dict(original_storage_report_restored_from_baseline=True,baseline_docs_sha256=hashlib.sha256((ROOT/'docs/storage-delivery-results.json').read_bytes()).hexdigest(),bulk_cleanup=False,ledger_reset=False,vhd_maintenance=False)
    path=ROOT/'docs/lifecycle-role-results.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(path=str(path),application_cases=len(result['independent_runs']['application_checks']['cases']),permission_matrix='NOT_RUN',page='NOT_RUN'),indent=2))
if __name__=='__main__':main()
