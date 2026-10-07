"""Administrator-owned fixed-action launcher. Kernel UID checks on Unix IPC.

Administrative access is a declared trusted boundary. No caller-supplied path,
shell command, model, target, receiver, environment, or process ID is accepted.
"""
import contextlib,grp,hashlib,json,os,secrets,shutil,socket,socketserver,sqlite3,subprocess,sys,threading,time
from pathlib import Path
from .deployment import BASE,CODE,RUN,BROKER,ROLES,EXPERIMENT,root,identity,hexid,policy,atomic,exact,receive,send,peer_uid,actor_environment
from .mpc import require,ProtocolError,settings,ROOT
from .processes import stop,quiescent,StopUnconfirmed
from .storage import record,Guard,estimate,history
from .deployment_diagnostics import failure,filtered
from .application import inference_plan
from .mpc import costs

LOCK=threading.Lock();ADMIN=BASE/'admin'
def report():return json.loads((CODE/'config/deployment-report.json').read_text())
def plan():return inference_plan(report(),'he','fss',policy()['allowed_targets'])
def codehash():return json.loads((CODE/'config/source-manifest.json').read_text())['sha256']
def database():
    conn=sqlite3.connect(ADMIN/'requests.sqlite');conn.execute('PRAGMA synchronous=FULL')
    conn.execute('CREATE TABLE IF NOT EXISTS requests(sid TEXT PRIMARY KEY, protocol_claimed INTEGER DEFAULT 0)');return conn
def registered(sid):
    hexid(sid);entry=record(sid)
    require(entry and entry['directory']==str(root('coordinator')/'build/requests'/sid),'BROKER_SESSION_BINDING')
    with contextlib.closing(database()) as conn:
        require(conn.execute('SELECT 1 FROM requests WHERE sid=?',(sid,)).fetchone(),'BROKER_UNKNOWN_REQUEST')
    return entry
def d(role,sid):return root(role)/'build/requests'/hexid(sid)
def spawn(role,args,pass_fds=()):
    entry=identity(role);groups=os.getgrouplist(entry.pw_name,entry.pw_gid)
    return subprocess.Popen(['/usr/bin/python3','-m',*args],cwd=root(role),env=actor_environment(role),
        user=entry.pw_uid,group=entry.pw_gid,extra_groups=groups,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,close_fds=True,pass_fds=pass_fds)
def actor(role,action,sid,attempt=None,digest=None):
    args=['src.isolated_actor',action,hexid(sid)]
    if attempt:args+=['--attempt',hexid(attempt,16)]
    if digest:args+=['--digest',hexid(digest,64)]
    proc=spawn(role,args)
    try:
        out,err=proc.communicate(timeout=300);quiescent([proc])
        if proc.returncode!=0:
            try:
                error=json.loads(out);code=error['actor_error'];diagnostic=filtered(error.get('actor_diagnostic'))
            except (ValueError,KeyError,TypeError):code='ROLE_OPERATION_FAILED';diagnostic=None
            require(isinstance(code,str) and code and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in code),'ROLE_OPERATION_FAILED')
            atomic(ADMIN/(sid+'-'+role+'-'+action+'-failure.json'),dict(role=role,action=action,error=code,diagnostic=diagnostic,time_ns=time.time_ns(),source_sha256=codehash()))
            raise ProtocolError(code)
        return json.loads(out)
    except BaseException:
        stop([proc]);raise
def chown_tree(path,role):
    entry=identity(role)
    for directory,dirs,files in os.walk(path,followlinks=False):
        for name in dirs+files:require(not (Path(directory)/name).is_symlink(),'ROLE_HANDOFF_SYMLINK')
        os.chown(directory,entry.pw_uid,entry.pw_gid);os.chmod(directory,0o700)
        for name in files:
            target=Path(directory)/name;require(target.stat().st_nlink==1,'ROLE_HANDOFF_HARDLINK')
            os.chown(target,entry.pw_uid,entry.pw_gid);os.chmod(target,0o600)
def permission_matrix():
    quiet_roles()
    public=policy();rows=[];secret=root('s0')/'build/assets/S0'/('model-'+public['model_id']+'.json')
    # Exercise the exact atomic writer under the service's restrictive umask.
    # These are mode-only fixtures; no secret or protocol material is generated.
    for role in ROLES:
        atomic(root(role)/'permission-atomic-public.json',dict(public_fixture=True,nodes=64),0o444)
        atomic(root(role)/'permission-atomic-private.json',dict(public_fixture=True))
    native=root('dealer')/'permission-native';native.mkdir(mode=0o750,exist_ok=True)
    os.chown(native,0,identity('dealer').pw_gid);os.chmod(native,0o750)
    shutil.copyfile(root('s0')/'build/assets/S0/he-layer0/parameters.seal',native/'parameters.seal');os.chmod(native/'parameters.seal',0o444)
    fd=os.open(secret,os.O_RDONLY);os.set_inheritable(fd,True)
    try:
        for role in ROLES:
            value=actor(role,'probe','0'*32)
            require(value['uid']==identity(role).pw_uid and value['euid']==identity(role).pw_uid,'PERMISSION_UID')
            require(all(row['pass_check'] for row in value['checks']),'PERMISSION_MATRIX_FAILED')
            require(value['startup_fds'].get('0')=='/dev/null' and all(key in ('0','1','2') for key in value['startup_fds']),'PERMISSION_DESCRIPTOR_LEAK')
            rows.append(value)
    finally:os.close(fd)
    value=dict(status='PASS_REAL_UID_MATRIX',timestamp_ns=time.time_ns(),source_sha256=codehash(),roles=rows,
        hardlink_audit=json.loads((ADMIN/'migration.json').read_text())['hardlink_audit'],
        administrator_access_retained=True,scope='Local OS deployment, half-honest parties and trusted offline dealer; not active security')
    atomic(ADMIN/'permissions.json',value);return value
def attested():
    path=ADMIN/'permissions.json'
    if not path.exists() or (ADMIN/'unsafe-stop.json').exists():return False
    doc=json.loads(path.read_text());return doc['status']=='PASS_REAL_UID_MATRIX' and doc['source_sha256']==codehash()

def quiet_roles():
    uids={identity(role).pw_uid for role in ('s0','s1','dealer','receiver')}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in path.read_text().splitlines() if ':' in line}
            if int(fields['Uid'].split()[1]) in uids and fields['State'][0] not in ('Z','X'):
                raise StopUnconfirmed('ROLE_PROCESS_STILL_LIVE')
        except FileNotFoundError:pass
        except (PermissionError,KeyError,ValueError):raise StopUnconfirmed('ROLE_PROCESS_STATE_UNREADABLE') from None

def backend(sid):
    entry=registered(sid);require(entry['state']=='running','BROKER_PROTOCOL_STATE')
    with contextlib.closing(database()) as conn,conn:
        row=conn.execute('SELECT protocol_claimed FROM requests WHERE sid=?',(sid,)).fetchone();require(row[0]==0,'BROKER_PROTOCOL_PERMANENTLY_CLAIMED')
        conn.execute('UPDATE requests SET protocol_claimed=1 WHERE sid=?',(sid,))
    sockets=socket.socketpair();procs=[];attempt=secrets.token_hex(8);started=time.perf_counter()
    try:
        guard=Guard(ROOT,sid,entry['budget']);guard.check(force=True)
        for number,role in enumerate(('s0','s1')):
            sock=sockets[number]
            procs.append(spawn(role,['src.mpc_worker',str(number),str(d(role,sid)),sid,'32',str(sock.fileno()),attempt],(sock.fileno(),)))
        for sock in sockets:sock.close()
        deadline=time.monotonic()+300
        while any(proc.poll() is None for proc in procs):
            guard.check()
            require(time.monotonic()<deadline,'ONLINE_TIMEOUT')
            for proc in procs:
                try:proc.communicate(timeout=.05)
                except subprocess.TimeoutExpired:pass
        proof=quiescent(procs)
        for proc in procs:
            _,err=proc.communicate(timeout=.5);require(proc.returncode==0 and not err,'WORKER_FAILED')
        metrics=[actor(role,'report',sid,attempt) for role in ('s0','s1')]
        require(all(value['success'] for value in metrics),'WORKER_FAILED')
        atomic(ADMIN/(sid+'-backend.json'),dict(attempt=attempt,proof=proof,metrics=metrics,wall_seconds=time.perf_counter()-started))
        return dict(attempt=attempt,proof=proof,metrics=metrics,wall_seconds=time.perf_counter()-started)
    except BaseException:
        proof=stop(procs);atomic(ADMIN/(sid+'-stop.json'),proof);raise
    finally:
        for sock in sockets:sock.close()

def command(request,uid):
    public=policy();admin=uid==public['operator_uid'];coordinator=uid==identity('coordinator').pw_uid
    require(admin or coordinator,'BROKER_PEER_UID_REJECTED')
    action=request.get('action')
    if action=='audit':exact(request,('action',));require(admin,'BROKER_ADMIN_ONLY');return permission_matrix()
    if action=='overview':exact(request,('action',));return dict(connected=attested(),source_sha256=codehash())
    if action=='fault_next':
        exact(request,('action',));require(admin,'BROKER_ADMIN_ONLY');quiet_roles();atomic(ADMIN/'fault-next.json',dict(phase='input'));return dict(armed=True)
    if action=='evidence':
        exact(request,('action',));require(admin,'BROKER_ADMIN_ONLY')
        return dict(migration=json.loads((ADMIN/'migration.json').read_text()),permissions=json.loads((ADMIN/'permissions.json').read_text()) if attested() else None,
            readiness_failures=[json.loads(path.read_text()) for path in sorted(ADMIN.glob('0'*32+'-*-probe-failure.json'))])
    if action in ('query_evidence','reuse_probe'):
        exact(request,('action','sid'));require(admin,'BROKER_ADMIN_ONLY');sid=hexid(request['sid']);entry=registered(sid)
        if action=='reuse_probe':
            require(entry['state'] in ('aborted','completed','cleaned'),'REUSE_PROBE_TERMINAL_ONLY')
            try:backend(sid)
            except ProtocolError as error:return dict(rejected=True,reason=str(error),protocol_reexecuted=False)
            raise ProtocolError('REUSE_PROBE_UNEXPECTED_ACCEPTANCE')
        identifiers_path=ADMIN/(sid+'-identifiers.json');identifiers=json.loads(identifiers_path.read_text()) if identifiers_path.exists() else None
        source=root('coordinator')/'results'/('query-'+sid+'.json')
        public_files=dict(dealer_public_plan=d('dealer',sid)/'public-plan.json',
            s0_job_template=d('s0',sid)/'job-template.json',s1_job_template=d('s1',sid)/'job-template.json')
        return dict(session=sid,state=entry['state'],batch=entry['batch'],identifiers=identifiers,
            lifecycle=history(sid),actor_failures=[json.loads(path.read_text()) for path in sorted(ADMIN.glob(sid+'-*-failure.json'))],
            public_file_modes={name:format(path.stat().st_mode&0o777,'04o') if path.exists() else None for name,path in public_files.items()},
            report=json.loads(source.read_text()) if source.exists() else None,
            cleanup_previews={r:{k:v for k,v in json.loads((ADMIN/(sid+'-'+r+'-cleanup.json')).read_text()).items() if k!='files'} for r in ('s0','s1','dealer') if (ADMIN/(sid+'-'+r+'-cleanup.json')).exists()})
    require(coordinator,'BROKER_COORDINATOR_ONLY');require(attested(),'REAL_UID_PERMISSIONS_NOT_ACCEPTED')
    fields=('action','sid','digest0','digest1','digest_dealer') if action=='clean_apply' else ('action','sid')
    exact(request,fields);sid=hexid(request['sid']);entry=record(sid)
    if action=='prepare':
        quiet_roles()
        require(entry and entry['state']=='generating' and entry['directory']==str(d('coordinator',sid)),'BROKER_SESSION_BINDING')
        require(entry['budget']>=estimate(plan(),costs(plan(),32))['total_bytes'],'BROKER_BUDGET_BINDING')
        with contextlib.closing(database()) as conn,conn:
            try:conn.execute('INSERT INTO requests(sid) VALUES (?)',(sid,))
            except sqlite3.IntegrityError:raise ProtocolError('BROKER_REQUEST_EXISTS') from None
        for role in ('s0','s1'):actor(role,'prepare',sid)
        dealer=d('dealer',sid);dealer.mkdir(mode=0o700);os.chown(dealer,identity('dealer').pw_uid,identity('dealer').pw_gid)
        for number in (0,1):
            path=dealer/f'S{number}';path.mkdir(mode=0o700);os.chown(path,identity('dealer').pw_uid,identity('dealer').pw_gid)
        source=root('s0')/'build/assets/S0/he-layer0/parameters.seal';shutil.copyfile(source,dealer/'parameters.seal');os.chmod(dealer/'parameters.seal',0o444)
        atomic(dealer/'public-plan.json',dict(session=sid,bits=32,plan=plan()),0o444)
        template=dict(session=sid,bits=32,operations=plan(),route='he',delivery=dict(model=report()['publication']['models'][-1],targets=public['allowed_targets'],receiver_id=public['receiver_id'],request_id=sid))
        for role in ('s0','s1'):atomic(d(role,sid)/'job-template.json',template,0o444)
        return dict(prepared=True,stopped=True)
    registered(sid)
    if action=='offline':
        require(entry['state']=='generating','BROKER_DEALER_STATE');result=actor('dealer','offline',sid)
        identifiers=json.loads((d('dealer',sid)/'material-identifiers.json').read_text())
        require(identifiers['batch']==entry['batch'],'BROKER_MATERIAL_BINDING')
        for number,role in enumerate(('s0','s1')):
            source=d('dealer',sid)/f'S{number}';target=d(role,sid)/f'S{number}'
            for name in ('preprocessing.json','ring-preprocessing'):
                path=source/name
                if not path.exists():continue
                require(not (target/name).exists(),'BROKER_MATERIAL_EXISTS');os.rename(path,target/name)
                if (target/name).is_dir():chown_tree(target/name,role)
                else:
                    require((target/name).stat().st_nlink==1,'ROLE_HANDOFF_HARDLINK');os.chown(target/name,identity(role).pw_uid,identity(role).pw_gid);os.chmod(target/name,0o600)
        atomic(ADMIN/(sid+'-identifiers.json'),identifiers)
        return dict(result,stopped=True,identifier_digest=hashlib.sha256(json.dumps(identifiers,sort_keys=True).encode()).hexdigest())
    if action=='input':
        fault=ADMIN/'fault-next.json'
        if fault.exists():fault.unlink();raise ProtocolError('INJECTED_INPUT_PREPARATION_FAILURE')
        require(entry['state']=='preparing','BROKER_INPUT_STATE')
        for role in ('s0','s1'):actor(role,'input',sid)
        return dict(stopped=True)
    if action=='protocol':return backend(sid)
    if action in ('export0','export1'):
        require(entry['state']=='running','BROKER_EXPORT_STATE');number=int(action[-1]);role='s'+str(number)
        saved=json.loads((ADMIN/(sid+'-backend.json')).read_text());actor(role,'export',sid,saved['attempt'])
        return dict(stopped=True,role=number,exported=True)
    if action=='receive':
        require(entry['state']=='running','BROKER_RECEIVER_STATE')
        destination=root('receiver')/'results/application'/EXPERIMENT/'receiver'/sid
        destination.mkdir(mode=0o700)
        os.chown(destination,identity('receiver').pw_uid,identity('receiver').pw_gid)
        try:
            for number,role in enumerate(('s0','s1')):
                source=d(role,sid)/'final'/f'S{number}.json';require(source.is_file(),'BROKER_PARTIAL_EXPORT')
                shutil.copyfile(source,destination/f'S{number}.json');os.chown(destination/f'S{number}.json',identity('receiver').pw_uid,identity('receiver').pw_gid);os.chmod(destination/f'S{number}.json',0o600)
            result=actor('receiver','receive',sid);atomic(ADMIN/(sid+'-result.json'),result)
            return dict(stopped=True,result=result)
        finally:
            # A shared recipient UID cannot read previous request exports.
            # Revoke directory traversal only after the recipient group stops.
            os.chown(destination,0,0);os.chmod(destination,0o700)
    if action=='terminate':
        quiet_roles()
        require(entry['state']=='stopping','BROKER_TERMINATE_STATE')
        proofs=[actor(role,'terminate',sid) for role in ('s0','s1')]
        return dict(stopped=True,receipts_saved=all(p['receipt_saved'] for p in proofs))
    if action=='clean_preview':
        quiet_roles()
        result={}
        for role in ('s0','s1','dealer'):
            doc=actor(role,'clean_preview',sid);atomic(ADMIN/(sid+'-'+role+'-cleanup.json'),doc)
            result[role]={k:v for k,v in doc.items() if k!='files'};result[role]['files_count']=len(doc['files'])
        return result
    if action=='clean_apply':
        quiet_roles()
        result=[]
        for number,role in enumerate(('s0','s1','dealer')):
            saved=json.loads((ADMIN/(sid+'-'+role+'-cleanup.json')).read_text())
            field='digest_dealer' if role=='dealer' else 'digest'+str(number)
            require(request[field]==saved['digest'],'BROKER_CLEAN_DIGEST')
            result.append(actor(role,'clean_apply',sid,digest=saved['digest']))
        return dict(roles=result,stopped=True)
    raise ProtocolError('BROKER_ACTION_REJECTED')

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(360)
        try:
            uid=peer_uid(self.request);require(uid in (policy()['operator_uid'],identity('coordinator').pw_uid),'BROKER_PEER_UID_REJECTED')
            request=receive(self.request)
            if request.get('action')=='overview':value=command(request,uid)
            else:
                with LOCK:value=command(request,uid)
            send(self.request,dict(ok=True,value=value))
        except BaseException as error:
            if getattr(error,'stopped',True) is False:atomic(ADMIN/'unsafe-stop.json',dict(error='STOP_UNCONFIRMED',time_ns=time.time_ns()))
            code=str(error).split(':',1)[0] if isinstance(error,ProtocolError) else 'ROLE_INTERFACE_FAILED'
            # Fixed-source location and errno only. Never persist stderr or
            # exception text; the operator uses a bounded metadata endpoint.
            if 'request' in locals() and isinstance(request,dict) and isinstance(request.get('sid'),str):
                try:
                    sid=hexid(request['sid']);registered(sid)
                    atomic(ADMIN/(sid+'-interface-failure.json'),dict(error=code,diagnostic=failure(error),time_ns=time.time_ns()))
                except (OSError,ProtocolError):pass
            try:send(self.request,dict(ok=False,error=code,stopped=getattr(error,'stopped',True)))
            except OSError:pass
class Server(socketserver.ThreadingUnixStreamServer):daemon_threads=False

def main():
    require(os.geteuid()==0,'BROKER_REQUIRES_ADMIN_UID');RUN.mkdir(parents=True,exist_ok=True)
    if BROKER.exists():BROKER.unlink()
    with Server(str(BROKER),Handler) as server:
        # Peer credentials, not caller-provided labels, authenticate requests.
        # Operator's already-running shell need not acquire new supplementary groups.
        os.chmod(BROKER,0o666);server.serve_forever()
if __name__=='__main__':main()
