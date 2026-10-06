"""Role-local irreversible termination receipt; no peer ledger access."""
import argparse, os, sqlite3
from .mpc import ROOT, require

def terminate(role,sid,batch):
    require(role in (0,1),'ROLE')
    require(all(len(v)==32 and all(c in '0123456789abcdef' for c in v) for v in (sid,batch)),'TERMINATION_BINDING')
    directory=ROOT/'state/mpc';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/f'S{role}-ledger.sqlite'
    with sqlite3.connect(path,timeout=15) as conn:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE IF NOT EXISTS batches (batch TEXT PRIMARY KEY, session TEXT, state TEXT)')
        conn.execute('INSERT OR IGNORE INTO batches VALUES (?,?,?)',(batch,sid,'aborted_burned'))
        row=conn.execute('SELECT session FROM batches WHERE batch=?',(batch,)).fetchone()
        require(row and row[0]==sid,'TERMINATION_BINDING')
        conn.execute("UPDATE batches SET state='aborted_burned' WHERE batch=?",(batch,))
    os.chmod(path,0o600)

def main():
    p=argparse.ArgumentParser();p.add_argument('role',type=int,choices=(0,1));p.add_argument('session');p.add_argument('batch');a=p.parse_args()
    terminate(a.role,a.session,a.batch)
if __name__=='__main__':main()
