"""Administrator-only read-only diagnosis of one existing deployment session.

No private shares, model contents, consumption ledger, credentials, arbitrary
paths, process launch, protocol execution, or state modification.
"""
import argparse,json,os,sqlite3,sys
from pathlib import Path
sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from src.deployment import BASE,CODE,hexid
from src.mpc import ProtocolError

def diagnose(sid,base=BASE,code=CODE):
    hexid(sid)
    gate=base/'gate/sessions.sqlite'
    with sqlite3.connect(gate.as_uri()+'?mode=ro',uri=True) as conn:
        row=conn.execute('SELECT state,batch,budget,detail FROM sessions WHERE sid=?',(sid,)).fetchone()
        if row is None:raise RuntimeError('DIAGNOSTIC_SESSION_UNKNOWN')
        events=[json.loads(r[0]) for r in conn.execute('SELECT body FROM events WHERE sid=? ORDER BY seq',(sid,))]
    query_db=base/'actors/coordinator/state/queries.sqlite'
    with sqlite3.connect(query_db.as_uri()+'?mode=ro',uri=True) as conn:
        rows=conn.execute('SELECT document FROM queries WHERE sid=?',(sid,)).fetchall()
    # Only metadata fields. Never print a token, client, result, path or raw
    # exception message; historical protocol error detail may contain paths.
    def code_only(value):
        value=str(value).split(':',1)[0]
        return value if value and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in value) else 'APPLICATION_FAILED'
    lifecycle=[]
    for event in events:
        value={k:event[k] for k in ('stage','time_ns','status') if k in event}
        if 'reason' in event:value['reason']=code_only(event['reason'])
        if isinstance(event.get('proof'),dict):value['stopped']=event['proof'].get('stopped') is True
        if event.get('stage')=='cleanup_observation':
            observation=event.get('observation',{})
            value['space']={k:observation.get(k) for k in (
                'deleted_file_allocated_bytes','unlinked_last_link_allocated_bytes',
                'removed_files','reclaimable_upper_bytes','observed_internal_available_delta',
                'observed_host_available_delta')}
            for label in ('space_before','space_after'):
                value['space'][label]={k:observation.get(label,{}).get(k) for k in
                    ('internal_available_bytes','host_available_bytes','host_status')}
        lifecycle.append(value)
    documents=[]
    for raw, in rows:
        doc=json.loads(raw)
        value={k:doc.get(k) for k in ('request_id','phase','terminal','delivery_state')}
        value['error']=code_only(doc['error']) if doc.get('error') else None
        value['has_result']=doc.get('result') is not None
        value['cost']={k:doc.get('cost',{}).get(k) for k in ('wall_seconds','wire_bytes','rounds')} if doc.get('cost') else None
        documents.append(value)
    failures=[v for v in lifecycle if v.get('status')=='failed']
    preparation={}
    for role in ('s0','s1','dealer'):
        actor=base/'actors'/role;request=actor/'build/requests'/sid
        own='S'+role[-1] if role!='dealer' else None
        source=actor/'build/assets'/own if own else None
        destination=request/own if own else request
        # Metadata only; no file opens. This identifies how far preparation
        # got even when the old executor emitted only ROLE_OPERATION_FAILED.
        source_files={p.relative_to(source):p.lstat() for p in source.rglob('*') if p.is_file() and not p.is_symlink()} if source and source.is_dir() else {}
        target_files={p.relative_to(destination):p.lstat() for p in destination.rglob('*') if p.is_file() and not p.is_symlink()} if destination.is_dir() else {}
        same=sum((info.st_dev,info.st_ino)==(target_files[name].st_dev,target_files[name].st_ino) for name,info in source_files.items() if name in target_files)
        preparation[role]=dict(request_directory_exists=request.is_dir(),source_file_count=len(source_files),request_file_count=len(target_files),same_inode_asset_links=same,
            request_owner_uid=request.stat().st_uid if request.exists() else None,
            source_device=source.stat().st_dev if source and source.exists() else None,
            request_device=request.stat().st_dev if request.exists() else None,
            public_plan_present=(request/'public-plan.json').is_file(),job_template_present=(request/'job-template.json').is_file())
    registry=base/'admin/requests.sqlite';claimed=None
    if registry.exists():
        with sqlite3.connect(registry.as_uri()+'?mode=ro',uri=True) as conn:
            registered=conn.execute('SELECT protocol_claimed FROM requests WHERE sid=?',(sid,)).fetchone()
            claimed=bool(registered[0]) if registered else None
    return dict(kind='ADMIN_READ_ONLY_EXISTING_SESSION_DIAGNOSTIC',session=sid,
        state=row[0],batch=row[1],reserved_bytes=row[2],lifecycle=lifecycle,
        failure=failures[-1] if failures else None,public_request_documents=documents,
        preparation=preparation,protocol_claimed=claimed,
        frozen_commit=json.loads((code/'config/source-manifest.json').read_text())['commit'],
        private_contents_disclosed=False,protocol_executed=False,state_modified=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',required=True);args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError('ADMIN_UID_REQUIRED: run in your local terminal with sudo; no password is accepted by this script')
    print(json.dumps(diagnose(args.session),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,sqlite3.Error,ValueError,ProtocolError) as error:
        print(json.dumps(dict(status='DIAGNOSTIC_FAILED',reason=str(error)),ensure_ascii=False),file=sys.stderr);sys.exit(1)
