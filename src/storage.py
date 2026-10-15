"""Fail-closed capacity guard and durable one-shot session lifecycle.
Local trusted coordinator policy, not an OS security boundary.
"""
import contextlib, fcntl, json, os, signal, sqlite3, threading, time
from pathlib import Path
from .mpc import ROOT, ProtocolError, require, settings

TERMINAL = {'completed', 'aborted', 'cleaned'}

def storage_directory():
    return Path(os.environ.get('PGNN_GATE_DIR',ROOT/'state/storage'))

def policy():
    return json.loads((ROOT/'config/storage.json').read_text())

def snapshot(directory, cfg=None):
    cfg = cfg or policy()
    v = os.statvfs(directory)
    result = {'internal_available_bytes': v.f_bavail*v.f_frsize,
              'host_available_bytes': None, 'host_status': 'UNKNOWN'}
    try:
        host = cfg['host']; mount = Path(host['mount']); vhd = Path(host['vhd'])
        require(os.environ.get('WSL_DISTRO_NAME') == host['distro'], 'HOST_DISTRO_BINDING')
        require(vhd.is_relative_to(mount) and vhd.is_file(), 'HOST_VHD_BINDING')
        entries = [line.split() for line in Path('/proc/mounts').read_text().splitlines()]
        require(any(row[1] == str(mount) and row[2] in ('9p', 'drvfs') for row in entries), 'HOST_MOUNT_BINDING')
        v = os.statvfs(mount)
        result.update(host_available_bytes=v.f_bavail*v.f_frsize, host_status='READABLE',
                      host_mount=str(mount), vhd=str(vhd), vhd_logical_bytes=vhd.stat().st_size)
    except (OSError, KeyError, ValueError, TypeError, ProtocolError) as error:
        result['host_error'] = str(error)
    return result

def estimate(plan, counts):
    # Both serialized role views, native ring triples/workspace, inputs/outputs,
    # SQLite growth and safety factor. No sparse/secret-value assumptions.
    require(all(type(count)==int and count>=0 for count in counts.values()),'DISK_PUBLIC_COUNT')
    sizes = {'boolean': 32, 'arithmetic': 96, 'dabit': 80, 'refresh': 40,
             'fss': 131072, 'he_mask': 128, 'rlwe_product': 0}
    material = sum(count*sizes.get(kind, 128) for kind, count in counts.items())
    ring = 0;trace=0
    for op in plan:
        if op.get('conversion') in ('private_decryption','legacy_ciphertext'):
            ctx = op['he']; limbs=len(ctx.get('data_moduli',settings()['he_coefficient_bits']))
            if op.get('conversion') == 'private_decryption':
                ring += 2*ctx['shape'][1]*ctx['degree']*limbs*8*24
            # Native eval saves multiply/extract ciphertexts per public row,
            # plus packed traces, for both roles. Include them explicitly.
            ciphertext_bound=ctx['degree']*limbs*2*8+4096
            if op.get('trace_ciphertexts',True):
                trace += 2*ctx['shape'][1]*(2*ctx['shape'][0]+1)*ciphertext_bound
    base = 64*1024**2
    return dict(material_bytes=material, native_work_bytes=ring, native_trace_bytes=trace, miscellaneous_bytes=base,
                total_bytes=int((material+ring+trace+base)*policy()['budget_multiplier']),
                method='Conservative public-count bound, paired JSON + native workspace/ciphertext traces + 64MiB, factor 2')

def db():
    directory = storage_directory(); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(directory/'sessions.sqlite', timeout=30)
    os.chmod(directory/'sessions.sqlite', 0o640 if os.environ.get('PGNN_GATE_DIR') else 0o600)
    conn.execute('PRAGMA synchronous=FULL')
    conn.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, directory TEXT UNIQUE, batch TEXT UNIQUE, state TEXT, budget INTEGER, detail TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, sid TEXT, body TEXT)')
    return conn

def record(sid):
    path=storage_directory()/'sessions.sqlite'
    if not path.exists():return None
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        row = conn.execute('SELECT directory,batch,state,budget,detail FROM sessions WHERE sid=?', (sid,)).fetchone()
    return dict(zip(('directory','batch','state','budget','detail'), row)) if row else None

def event(sid,stage,**fields):
    body=dict(stage=stage,time_ns=time.time_ns(),**fields)
    with contextlib.closing(db()) as conn, conn:
        conn.execute('INSERT INTO events(sid,body) VALUES (?,?)',(sid,json.dumps(body,sort_keys=True)))
    return body

def history(sid):
    path=storage_directory()/'sessions.sqlite'
    if not path.exists():return []
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():return []
        return [json.loads(row[0]) for row in conn.execute('SELECT body FROM events WHERE sid=? ORDER BY seq',(sid,))]

def stopped(sid):
    proofs=[row['proof'] for row in history(sid) if 'proof' in row]
    return bool(proofs and proofs[-1].get('stopped') is True)

def committed(sid):
    entry=record(sid)
    if not entry:return False
    if entry['state']=='completed':return True
    if entry['state']=='cleaned':
        return json.loads(entry['detail']).get('termination_state')=='completed'
    return False

def public_status(sid):
    """Authoritative allowlisted state; never return paths, ledgers or shares.

    Cached application JSON is not completion evidence when its persistence
    failed. The durable event stream and tombstone override it.
    """
    entry=record(sid);require(entry is not None,'SESSION_UNKNOWN')
    events=history(sid);termination=entry['state']
    if termination=='cleaned':termination=json.loads(entry['detail']).get('termination_state')
    failures=[row for row in events if row.get('status')=='failed' and row['stage'] not in ('failure_report_save','failure_retention')]
    exports=[role for role in (0,1) if any(row['stage']==f'export_S{role}' and row.get('status')=='persisted' for row in events)]
    complete=termination=='completed' and any(row['stage']=='completed' for row in events) and exports==[0,1]
    reason=None
    if failures:
        raw=failures[-1]['reason'];kind,_,detail=raw.partition(':')
        reason={'OSError':'IO_ERROR','KeyboardInterrupt':'INTERRUPTED','CalledProcessError':'ROLE_COMMAND_FAILED','StopUnconfirmed':'STOP_UNCONFIRMED'}.get(kind,'APPLICATION_FAILED')
        if kind=='ProtocolError':
            code=detail.split(':',1)[0]
            if code and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in code):reason=code
    return dict(session=sid,state=entry['state'],termination_state=termination,
        stage=events[-1]['stage'] if events else 'legacy_no_event_journal',
        stopped=stopped(sid),delivery_state='complete' if complete else ('incomplete' if termination in ('aborted','stopping') else 'pending'),
        exported_roles=exports,failure_stage=failures[-1]['stage'] if failures else None,
        failure_reason=reason)

_workflows=threading.local()
@contextlib.contextmanager
def workflow_lease(sid):
    # Delivery lock is separate from the protocol/dealer lock. Same-thread
    # nesting permits automatic cleanup; another process/thread cannot enter.
    require(len(sid)==32 and all(c in '0123456789abcdef' for c in sid),'STORAGE_SESSION_ID')
    owned=getattr(_workflows,'owned',set())
    if sid in owned:
        yield;return
    directory=storage_directory();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (directory/(sid+'.workflow.lock')).open('a') as file:
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ProtocolError('SESSION_ACTIVE') from None
        _workflows.owned=owned|{sid}
        try:yield
        finally:_workflows.owned=owned

@contextlib.contextmanager
def lease(sid, suffix='.lock'):
    require(len(sid)==32 and all(c in '0123456789abcdef' for c in sid), 'STORAGE_SESSION_ID')
    require(suffix in ('.lock','.workflow.lock'),'STORAGE_LOCK_TYPE')
    directory = storage_directory(); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory/(sid+suffix)).open('a') as file:
        try: fcntl.flock(file, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ProtocolError('SESSION_ACTIVE') from None
        yield

def check(directory, budget=0, exclude=None, probe=None, cfg=None):
    cfg = cfg or policy(); status = (probe or snapshot)(directory, cfg)
    path=storage_directory()/'sessions.sqlite';reservations=0
    if path.exists():
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
            reservations = conn.execute("SELECT COALESCE(SUM(budget),0) FROM sessions WHERE state IN ('generating','ready','preparing','running','stopping') AND sid != ?", (exclude or '',)).fetchone()[0]
    status.update(required_growth_bytes=budget+reservations,
                  internal_reserve_bytes=cfg['internal_reserve_bytes'], host_reserve_bytes=cfg['host_reserve_bytes'])
    if status['host_available_bytes'] is None:
        raise ProtocolError('HOST_SPACE_UNKNOWN:'+json.dumps(status, sort_keys=True))
    if status['internal_available_bytes'] < budget+reservations+cfg['internal_reserve_bytes']:
        raise ProtocolError('INTERNAL_SPACE_LOW:'+json.dumps(status, sort_keys=True))
    if status['host_available_bytes'] < budget+reservations+cfg['host_reserve_bytes']:
        raise ProtocolError('HOST_SPACE_LOW:'+json.dumps(status, sort_keys=True))
    return status

def begin(directory, sid, batch, budget):
    # Serialize admission decisions across concurrent dealers.
    with lease('0'*32):
        check(directory, budget)
        with contextlib.closing(db()) as conn, conn:
            try: conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)', (sid,str(Path(directory).resolve()),batch,'generating',budget,''))
            except sqlite3.IntegrityError: raise ProtocolError('SESSION_ALREADY_REGISTERED') from None

def transition(sid, expected, state, detail=''):
    with contextlib.closing(db()) as conn, conn:
        row = conn.execute('SELECT state FROM sessions WHERE sid=?', (sid,)).fetchone()
        require(row and row[0] in expected, 'SESSION_STATE_REJECTED')
        conn.execute('UPDATE sessions SET state=?,detail=? WHERE sid=?', (state,detail,sid))

class Guard:
    def __init__(self, directory, sid, budget=0):
        self.directory=directory; self.sid=sid; self.budget=budget; self.last=0; self.interval=policy()['monitor_seconds']
    def check(self, force=False):
        now=time.monotonic()
        if force or now-self.last >= self.interval:
            status=check(self.directory,self.budget,self.sid); self.last=now; return status

def reject_burned(batch):
    # Role readers never create/chmod/write the coordinator database.
    path=storage_directory()/'sessions.sqlite'
    if not path.exists():return
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        row=conn.execute('SELECT state FROM sessions WHERE batch=?', (batch,)).fetchone()
    require(not row or row[0] in ('ready','running'), 'SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE')

def burn(sid, detail, *, stopped=False):
    entry=record(sid)
    if not entry: return
    # Central tombstone committed first: even a role-ledger I/O failure cannot
    # make a restored bundle usable through Materials on restart.
    # Pending notifications are related processes too. Do not expose a
    # cleanable abort until their process groups have also stopped.
    transition(sid, {'generating','ready','preparing','running','aborted','stopping'}, 'stopping', detail)
    event(sid,'termination_pending',reason=detail,proof=dict(stopped=False),state='stopping')
    confirmed=stopped
    # The role helper, never the coordinator, owns writes to its consumption
    # ledger. Real OS identity deployment is separately gated and verified.
    from .processes import run
    import sys
    for role in (0,1):
        try:run([sys.executable,'-m','src.role_state',str(role),sid,entry['batch']],cwd=ROOT,timeout=15)
        except BaseException as error:
            # A stopped notifier that failed to persist its receipt is also
            # incomplete termination. Keep cleanup blocked, with central reuse
            # refusal already durable, until an independently checked receipt.
            confirmed=False
            fields={}
            if getattr(error,'stopped',True) is False:
                transition(sid,{'aborted','stopping'},'stopping',detail+'; termination helper stop unconfirmed')
                fields['proof']=dict(stopped=False)
            event(sid,'role_termination_notification_failed',role=role,reason=str(error),**fields)
    if confirmed:transition(sid,{'stopping'},'aborted',detail)
    event(sid,'termination',reason=detail,proof=dict(stopped=confirmed),state='aborted' if confirmed else 'stopping')

@contextlib.contextmanager
def abort_signals():
    if threading.current_thread() is not threading.main_thread():
        yield;return
    previous=signal.getsignal(signal.SIGTERM)
    def terminate(signum,frame):raise ProtocolError('TERMINATED_BURN_SESSION')
    signal.signal(signal.SIGTERM,terminate)
    try:yield
    finally:signal.signal(signal.SIGTERM,previous)
