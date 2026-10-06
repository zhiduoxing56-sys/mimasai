"""Fail-closed capacity guard and durable one-shot session lifecycle.
Local trusted coordinator policy, not an OS security boundary.
"""
import contextlib, fcntl, json, os, signal, sqlite3, threading, time
from pathlib import Path
from .mpc import ROOT, ProtocolError, require

TERMINAL = {'completed', 'aborted', 'cleaned'}

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
        if op.get('conversion') == 'private_decryption':
            ctx = op['he']; ring += 2*ctx['shape'][1]*ctx['degree']*len(ctx['data_moduli'])*8*24
            # Native eval saves multiply/extract ciphertexts per public row,
            # plus packed traces, for both roles. Include them explicitly.
            ciphertext_bound=ctx['degree']*len(ctx['data_moduli'])*2*8+4096
            trace += 2*ctx['shape'][1]*(2*ctx['shape'][0]+1)*ciphertext_bound
    base = 64*1024**2
    return dict(material_bytes=material, native_work_bytes=ring, native_trace_bytes=trace, miscellaneous_bytes=base,
                total_bytes=int((material+ring+trace+base)*policy()['budget_multiplier']),
                method='Conservative public-count bound, paired JSON + native workspace/ciphertext traces + 64MiB, factor 2')

def db():
    directory = ROOT/'state/storage'; directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(directory/'sessions.sqlite', timeout=30)
    os.chmod(directory/'sessions.sqlite', 0o600)
    conn.execute('PRAGMA synchronous=FULL')
    conn.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, directory TEXT UNIQUE, batch TEXT UNIQUE, state TEXT, budget INTEGER, detail TEXT)')
    return conn

def record(sid):
    with contextlib.closing(db()) as conn:
        row = conn.execute('SELECT directory,batch,state,budget,detail FROM sessions WHERE sid=?', (sid,)).fetchone()
    return dict(zip(('directory','batch','state','budget','detail'), row)) if row else None

@contextlib.contextmanager
def lease(sid):
    require(len(sid)==32 and all(c in '0123456789abcdef' for c in sid), 'STORAGE_SESSION_ID')
    directory = ROOT/'state/storage'; directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory/(sid+'.lock')).open('a') as file:
        try: fcntl.flock(file, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ProtocolError('SESSION_ACTIVE') from None
        yield

def check(directory, budget=0, exclude=None, probe=None, cfg=None):
    cfg = cfg or policy(); status = (probe or snapshot)(directory, cfg)
    with contextlib.closing(db()) as conn:
        reservations = conn.execute("SELECT COALESCE(SUM(budget),0) FROM sessions WHERE state IN ('generating','ready','running') AND sid != ?", (exclude or '',)).fetchone()[0]
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
    with contextlib.closing(db()) as conn:
        row=conn.execute('SELECT state FROM sessions WHERE batch=?', (batch,)).fetchone()
    require(not row or row[0] in ('ready','running'), 'SESSION_MATERIAL_PERMANENTLY_UNAVAILABLE')

def burn(sid, detail):
    entry=record(sid)
    if not entry: return
    # Central tombstone committed first: even a role-ledger I/O failure cannot
    # make a restored bundle usable through Materials on restart.
    transition(sid, {'generating','ready','running','aborted'}, 'aborted', detail)
    for role in (0,1):
        path=ROOT/'state/mpc'/f'S{role}-ledger.sqlite'
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(path, timeout=30) as conn:
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('CREATE TABLE IF NOT EXISTS batches (batch TEXT PRIMARY KEY, session TEXT, state TEXT)')
            conn.execute('INSERT OR IGNORE INTO batches VALUES (?,?,?)', (entry['batch'],sid,'aborted_burned'))
            conn.execute("UPDATE batches SET state='aborted_burned' WHERE batch=?", (entry['batch'],))
        os.chmod(path,0o600)

@contextlib.contextmanager
def abort_signals():
    if threading.current_thread() is not threading.main_thread():
        yield;return
    previous=signal.getsignal(signal.SIGTERM)
    def terminate(signum,frame):raise ProtocolError('TERMINATED_BURN_SESSION')
    signal.signal(signal.SIGTERM,terminate)
    try:yield
    finally:signal.signal(signal.SIGTERM,previous)
