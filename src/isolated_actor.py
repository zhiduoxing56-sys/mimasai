"""Fixed actor operations, executed after the privileged launcher drops UID.

No generic file or command API. Each ROOT is behind an administrator-owned
role boundary. Dealer correlation generation remains explicitly trusted.
"""
import argparse,hashlib,json,os,shutil,sys,time
from pathlib import Path
from .mpc import ROOT,require,settings,ProtocolError
from .deployment import root,identity,hexid,atomic,policy

def own_role():
    role=ROOT.name;require(ROOT==root(role) and os.geteuid()==identity(role).pw_uid,'ACTOR_UID_BINDING')
    return role
def directory(sid):return ROOT/'build/requests'/hexid(sid)
def digest(doc):return hashlib.sha256(json.dumps(doc,sort_keys=True).encode()).hexdigest()
def clones(source,target):
    for path in source.rglob('*'):
        relative=path.relative_to(source);require(not path.is_symlink(),'ASSET_SYMLINK')
        if path.is_dir():(target/relative).mkdir(parents=True,exist_ok=True,mode=0o700)
        elif path.is_file():os.link(path,target/relative)
def operation(action,sid,attempt=None,expected=None):
    role=own_role();d=directory(sid);public=policy()
    if action=='offline':
        require(role=='dealer','ACTOR_OPERATION')
        from .offline import _generate
        from .storage import record,Guard,estimate
        from .mpc import costs
        doc=json.loads((d/'public-plan.json').read_text());entry=record(sid)
        require(entry and entry['state']=='generating' and doc['session']==sid,'DEALER_SESSION')
        guard=Guard(d,sid,entry['budget']);guard.check(force=True);started=time.perf_counter()
        result=_generate(d,sid,doc['bits'],doc['plan'],None,entry['batch'],guard)
        result['disk_budget']=estimate(doc['plan'],costs(doc['plan'],doc['bits']));result['offline_wall_seconds']=time.perf_counter()-started
        return result
    if action=='receive':
        require(role=='receiver','ACTOR_OPERATION')
        from .receiver import receive
        from .public_projection import final
        received=ROOT/'results/application'/public['experiment_id']/'receiver'/sid
        return final(receive(received,public['receiver_id']),public,sid)
    require(role in ('s0','s1'),'ACTOR_OPERATION');number=int(role[-1]);own='S'+str(number)
    if action=='prepare':
        (d/own).mkdir(parents=True,mode=0o700)
        clones(ROOT/'build/assets'/own,d/own)
        return dict(prepared=True)
    if action=='input':
        from .role_io import main
        sys.argv=['role_io','query_input',str(number),str(ROOT/'build/assets'),str(d)];main()
        return None # role_io has emitted only its completion metadata.
    if action=='report':
        hexid(attempt,16);doc=json.loads((d/own/f'metrics-{attempt}.json').read_text())
        c=doc.get('communication');communication={key:c[key] for key in ('bytes_sent','exchange_rounds')} if c else None
        return dict(role=number,success=doc['success'],error=doc.get('error','WORKER_FAILED') if not doc['success'] else None,communication=communication)
    if action=='export':
        from .role_io import main
        hexid(attempt,16);target=d/'final';target.mkdir(mode=0o700)
        sys.argv=['role_io','export',str(number),str(d),str(target),'--attempt',attempt];main()
        return None
    if action=='terminate':
        from .storage import record
        from .role_state import terminate
        entry=record(sid);require(entry and entry['state']=='stopping','ACTOR_TERMINATION')
        terminate(number,sid,entry['batch']);return dict(receipt_saved=True)
    if action in ('clean_preview','clean_apply'):
        from .storage import record,stopped,TERMINAL
        from .retention import manifest
        entry=record(sid);require(entry and entry['state'] in TERMINAL and stopped(sid),'ACTOR_CLEAN_STATE')
        doc=dict(session=sid,role=number,**manifest(d));value=digest(doc)
        if action=='clean_preview':return dict(doc,digest=value)
        require(expected==value,'CLEAN_PREVIEW_CHANGED');removed=[]
        for row in doc['files']:
            path=d/row['path'];require(path.relative_to(d).parts[0]==own and not path.is_symlink(),'ACTOR_CLEAN_PATH')
            st=path.stat();require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)==(row['device'],row['inode'],row['bytes'],row['mtime_ns']),'CLEAN_PREVIEW_CHANGED')
            path.unlink();removed.append(dict(allocated=st.st_blocks*512,last=st.st_nlink==1))
            fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
        return dict(removed_files=len(removed),deleted_file_allocated_bytes=sum(r['allocated'] for r in removed),unlinked_last_link_allocated_bytes=sum(r['allocated'] for r in removed if r['last']))
    raise ValueError('ACTOR_OPERATION')

def probe():
    role=own_role();public=policy();base=root(role);model='model-'+public['model_id']+'.json'
    targets={
        'own_model':(base/'build/assets'/('S'+role[-1])/model,role in ('s0','s1')),
        's0_model':(root('s0')/'build/assets/S0'/model,role=='s0'),
        's1_model':(root('s1')/'build/assets/S1'/model,role=='s1'),
        's0_ledger':(root('s0')/'state/mpc/S0-ledger.sqlite',role=='s0'),
        's1_ledger':(root('s1')/'state/mpc/S1-ledger.sqlite',role=='s1'),
        's0_input':(root('s0')/'build/assets/S0/input-shares.json',role=='s0'),
        's1_input':(root('s1')/'build/assets/S1/input-shares.json',role=='s1'),
        's0_online_messages':(root('s0')/'build/permission-messages',role=='s0'),
        's1_online_messages':(root('s1')/'build/permission-messages',role=='s1'),
        'authorized_final':(root('receiver')/'permission-current/S0.json',role=='receiver'),
        'other_request_final':(root('receiver')/'permission-other/S0.json',False),
        'verification_directory':(Path(public['original_workspace'])/'verification',False),
        'original_private_data':(Path(public['original_workspace'])/'build/application'/public['experiment_id']/'V/data.json',False),
        'public_plan':(base/'permission-public-plan.json',True),
        'public_code':(Path(public['code'])/'src/mpc.py',True),
        'public_config':(Path(public['code'])/'config/phase0.json',True),
        'central_gate_read':(Path('/var/lib/privacy-gnn/gate/sessions.sqlite'),role in ('s0','s1','dealer','coordinator')),
    }
    if role not in ('s0','s1'):targets.pop('own_model')
    rows=[]
    for label,(path,expected) in targets.items():
        try:fd=os.open(path,os.O_RDONLY| (os.O_DIRECTORY if label=='verification_directory' else 0));os.close(fd);allowed=True;error=None
        except OSError as e:allowed=False;error=e.errno
        rows.append(dict(resource=label,expected='ALLOW' if expected else 'DENY',actual='ALLOW' if allowed else 'DENY',errno=error,pass_check=allowed==expected and (allowed or error in (1,13)),contents_read=False))
    for label,path,expected in [('code_write',Path(public['code'])/'src/mpc.py',False),('config_write',Path(public['code'])/'config/phase0.json',False),('central_gate_write',Path('/var/lib/privacy-gnn/gate/sessions.sqlite'),role=='coordinator')]:
        try:fd=os.open(path,os.O_WRONLY);os.close(fd);allowed=True
        except PermissionError:allowed=False
        rows.append(dict(resource=label,expected='ALLOW' if expected else 'DENY',actual='ALLOW' if allowed else 'DENY',pass_check=allowed==expected,contents_written=False))
    from .deployment import call,BROKER,PUBLIC_API,RemoteError
    for label,path,expected in [('role_executor_peer',BROKER,role=='coordinator'),('public_api_peer',PUBLIC_API,role=='page')]:
        try:call(path,dict(action='overview'),timeout=3);allowed=True;reason=None
        except RemoteError as error:allowed=False;reason=str(error)
        except PermissionError:allowed=False;reason='OS_DAC_DENIED'
        rows.append(dict(resource=label,expected='ALLOW' if expected else 'DENY',actual='ALLOW' if allowed else 'DENY',pass_check=allowed==expected,reason=reason))
    fds={}
    for path in Path('/proc/self/fd').iterdir():
        try:fds[path.name]=os.readlink(path)
        except FileNotFoundError:pass
    return dict(role=role,uid=os.getuid(),euid=os.geteuid(),groups=os.getgroups(),checks=rows,startup_fds=fds)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','offline','input','report','export','receive','terminate','clean_preview','clean_apply','probe'));p.add_argument('sid');p.add_argument('--attempt');p.add_argument('--digest');a=p.parse_args()
    result=probe() if a.action=='probe' else operation(a.action,hexid(a.sid),a.attempt,a.digest)
    if result is not None:print(json.dumps(result,separators=(',',':')))
if __name__=='__main__':
    try:main()
    except BaseException as error:
        raw=str(error).split(':',1)[0] if isinstance(error,ProtocolError) else 'ROLE_OPERATION_FAILED'
        code=raw if raw and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in raw) else 'ROLE_OPERATION_FAILED'
        print(json.dumps(dict(actor_error=code)),flush=True);sys.exit(1)
