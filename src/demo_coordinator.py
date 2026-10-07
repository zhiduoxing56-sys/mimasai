"""Unprivileged query lifecycle. Only metadata and authorized final results."""
import contextlib,grp,hashlib,hmac,json,os,secrets,socketserver,sqlite3,threading,time
from pathlib import Path
from .deployment import BASE,CODE,RUN,BROKER,PUBLIC_API,root,identity,policy,exact,hexid,atomic,call,receive,send,peer_uid,RemoteError
from .storage import begin,record,transition,event,workflow_lease,Guard,estimate,snapshot
from .mpc import require,costs,ProtocolError
from .application import inference_plan

ACTIVE=threading.Lock();DB_LOCK=threading.Lock();STOPPED=False
def db():
    conn=sqlite3.connect(root('coordinator')/'state/queries.sqlite',timeout=30);conn.execute('PRAGMA synchronous=FULL')
    conn.execute('CREATE TABLE IF NOT EXISTS clients(client TEXT PRIMARY KEY,expires REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS queries(token TEXT PRIMARY KEY,client TEXT,sid TEXT,document TEXT)');return conn
def save(token,client,doc):
    with DB_LOCK,contextlib.closing(db()) as conn,conn:conn.execute('UPDATE queries SET document=? WHERE token=? AND client=?',(json.dumps(doc),token,client))
def loaded(token,client):
    with DB_LOCK,contextlib.closing(db()) as conn:row=conn.execute('SELECT document FROM queries WHERE token=? AND client=?',(token,client)).fetchone()
    require(row,'REQUEST_CAPABILITY_REJECTED');return json.loads(row[0])
def broker(action,sid,**fields):return call(BROKER,dict(action=action,sid=sid,**fields))
def connected():
    try:return call(BROKER,dict(action='overview'),timeout=2)['connected'] and not STOPPED
    except (OSError,ProtocolError):return False
def cleanup(sid):
    before=snapshot(root('coordinator'));preview=broker('clean_preview',sid)
    current=record(sid);termination=current['state']
    transition(sid,{'completed','aborted'},'cleaned',json.dumps(dict(termination_state=termination,role_previews=preview)))
    result=broker('clean_apply',sid,digest0=preview['s0']['digest'],digest1=preview['s1']['digest'],digest_dealer=preview['dealer']['digest']);after=snapshot(root('coordinator'))
    observation=dict(space_before=before,space_after=after,deleted_file_allocated_bytes=sum(v['deleted_file_allocated_bytes'] for v in result['roles']),
        unlinked_last_link_allocated_bytes=sum(v['unlinked_last_link_allocated_bytes'] for v in result['roles']),removed_files=sum(v['removed_files'] for v in result['roles']),
        reclaimable_upper_bytes=sum(preview[r]['reclaimable_upper_bytes'] for r in ('s0','s1','dealer')),
        observed_internal_available_delta=after['internal_available_bytes']-before['internal_available_bytes'],
        observed_host_available_delta=after['host_available_bytes']-before['host_available_bytes'] if None not in (after['host_available_bytes'],before['host_available_bytes']) else None,
        interpretation='Deletion blocks and observed filesystem deltas are separate; no claim of actual VHD reclamation.')
    event(sid,'cleanup_observation',observation=observation);return observation

def run_query(token,client,doc):
    global STOPPED
    sid=doc['request_id'];started=time.perf_counter();registered=False;prepared=False;phase='admission';offline=None;online=None
    def step(value):
        nonlocal phase
        phase=value;doc['phase']=value;doc['cost']=dict(wall_seconds=time.perf_counter()-started,wire_bytes=online['wire_bytes'] if online else None,rounds=online['rounds'] if online else None)
        save(token,client,doc)
        if registered:event(sid,value,status='started')
    try:
        with workflow_lease(sid):
            public=policy();report=json.loads((CODE/'config/deployment-report.json').read_text());plan=inference_plan(report,'he','fss',public['allowed_targets'])
            directory=root('coordinator')/'build/requests'/sid;directory.mkdir(mode=0o700)
            budget=estimate(plan,costs(plan,32));begin(directory,sid,secrets.token_hex(16),budget['total_bytes']);registered=True
            step('admission');prepared=True;broker('prepare',sid)
            step('offline');offline=broker('offline',sid);transition(sid,{'generating'},'ready')
            transition(sid,{'ready'},'preparing');step('input');Guard(directory,sid,budget['total_bytes']).check(force=True);broker('input',sid)
            transition(sid,{'preparing'},'running');step('online');backend=broker('protocol',sid)
            require(backend['proof']['stopped'],'BACKEND_STOP_UNCONFIRMED');event(sid,'backend_stopped',proof=backend['proof'])
            metrics=backend['metrics'];online=dict(wall_seconds=backend['wall_seconds'],wire_bytes=sum(v['communication']['bytes_sent'] for v in metrics),rounds=metrics[0]['communication']['exchange_rounds'])
            step('export')
            for number in (0,1):
                broker('export'+str(number),sid);event(sid,'export_S'+str(number),status='persisted',receiver_id=public['receiver_id'])
            step('receiver');received=broker('receive',sid);require(received['stopped'],'RECEIVER_STOP_UNCONFIRMED')
            # Keep the result withheld until delivery evidence is durable.
            private_record=dict(request_id=sid,offline=offline,online=online,source_iteration=160,model_id=public['model_id'],result=received['result'],authorized_receiver=public['receiver_id'],full_state_restored=False)
            destination=root('coordinator')/'results'/('query-'+sid+'.json');atomic(destination,private_record)
            transition(sid,{'running'},'completed','Authorized receiver final result and run report persisted');event(sid,'completed',status='complete',proof=dict(stopped=True))
            step('complete');private_record['retention']=cleanup(sid);private_record['wall_seconds']=time.perf_counter()-started;atomic(destination,private_record)
            doc.update(phase='complete',terminal=True,delivery_state='complete',result=received['result'],error=None,
                cost=dict(wall_seconds=private_record['wall_seconds'],wire_bytes=online['wire_bytes'],rounds=online['rounds']))
            save(token,client,doc)
    except BaseException as error:
        code=str(error).split(':',1)[0] if isinstance(error,ProtocolError) else 'APPLICATION_FAILED'
        doc.update(phase='failed',terminal=True,delivery_state='incomplete',result=None,error=code,
            cost=dict(wall_seconds=time.perf_counter()-started,wire_bytes=online['wire_bytes'] if online else None,rounds=online['rounds'] if online else None))
        if registered:
            event(sid,phase,status='failed',reason=code)
            entry=record(sid)
            if entry['state'] not in ('completed','cleaned'):
                transition(sid,{'generating','ready','preparing','running','stopping'},'stopping',code)
                event(sid,'termination_pending',proof=dict(stopped=False))
                confirmed=getattr(error,'stopped',True)
                if prepared and confirmed:
                    try:confirmed=broker('terminate',sid)['receipts_saved']
                    except BaseException:confirmed=False
                if confirmed:
                    transition(sid,{'stopping'},'aborted',code);event(sid,'termination',proof=dict(stopped=True),reason=code)
                    try:doc['retention']=cleanup(sid)
                    except BaseException:event(sid,'cleanup_failed',reason='ROLE_CLEANUP_FAILED')
                else:doc['phase']='stopping';STOPPED=True
        save(token,client,doc)
    finally:ACTIVE.release()

def command(request):
    action=request.get('action')
    if action=='overview':exact(request,('action',));return dict(connected=connected())
    if action=='authorize':
        exact(request,('action','client','access'));client=hexid(request['client'],48);access=hexid(request['access'],64)
        require(hmac.compare_digest(hashlib.sha256(access.encode()).hexdigest(),policy()['access_sha256']),'LOCAL_AUTHORIZATION_REJECTED')
        with DB_LOCK,contextlib.closing(db()) as conn,conn:conn.execute('INSERT OR REPLACE INTO clients VALUES (?,?)',(client,time.time()+8*3600))
        return dict(authorized=True)
    exact(request,('action','client','token'));require(action in ('submit','status'),'PUBLIC_ACTION_REJECTED');client=hexid(request['client'],48);token=hexid(request['token'])
    with DB_LOCK,contextlib.closing(db()) as conn:
        row=conn.execute('SELECT expires FROM clients WHERE client=?',(client,)).fetchone();require(row and row[0]>time.time(),'LOCAL_AUTHORIZATION_REQUIRED')
        existing=conn.execute('SELECT document FROM queries WHERE token=? AND client=?',(token,client)).fetchone()
    if existing:return json.loads(existing[0])
    require(action=='submit','REQUEST_CAPABILITY_REJECTED');require(connected(),'REAL_BACKEND_NOT_CONNECTED')
    require(ACTIVE.acquire(blocking=False),'QUERY_BUSY')
    doc=dict(request_id=secrets.token_hex(16),phase='admission',terminal=False,delivery_state='pending',result=None,cost=None,error=None)
    try:
        with DB_LOCK,contextlib.closing(db()) as conn,conn:
            try:conn.execute('INSERT INTO queries VALUES (?,?,?,?)',(token,client,doc['request_id'],json.dumps(doc)))
            except sqlite3.IntegrityError:raise ProtocolError('REQUEST_CAPABILITY_REJECTED') from None
        thread=threading.Thread(target=run_query,args=(token,client,doc.copy()),daemon=False);thread.start()
    except BaseException:ACTIVE.release();raise
    return doc

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            require(peer_uid(self.request)==identity('page').pw_uid,'PUBLIC_PEER_UID_REJECTED');value=command(receive(self.request));send(self.request,dict(ok=True,value=value))
        except BaseException as error:
            code=str(error).split(':',1)[0] if isinstance(error,ProtocolError) else 'PUBLIC_INTERFACE_FAILED'
            try:send(self.request,dict(ok=False,error=code))
            except OSError:pass
class Server(socketserver.ThreadingUnixStreamServer):daemon_threads=False
def recover_pending():
    global STOPPED
    with contextlib.closing(db()) as conn:
        old=conn.execute('SELECT token,client,document FROM queries').fetchall()
    for token,client,raw in old:
        doc=json.loads(raw)
        if not doc['terminal'] or doc['phase']=='stopping':
            entry=record(doc['request_id'])
            if entry and entry['state'] in ('generating','ready','preparing','running','stopping'):
                transition(doc['request_id'],{entry['state']},'stopping','RESTART_REQUIRES_STOP_CONFIRMATION')
                event(doc['request_id'],'termination_pending',proof=dict(stopped=False),reason='RESTART_REQUIRES_STOP_CONFIRMATION')
            doc.update(phase='stopping',terminal=True,delivery_state='incomplete',result=None,error='RESTART_REQUIRES_STOP_CONFIRMATION');save(token,client,doc);STOPPED=True
def main():
    require(os.geteuid()==identity('coordinator').pw_uid,'COORDINATOR_UID');recover_pending()
    if PUBLIC_API.exists():PUBLIC_API.unlink()
    with Server(str(PUBLIC_API),Handler) as server:
        os.chmod(PUBLIC_API,0o660);os.chown(PUBLIC_API,-1,grp.getgrnam('pgnn-page-api').gr_gid);server.serve_forever()
if __name__=='__main__':main()
