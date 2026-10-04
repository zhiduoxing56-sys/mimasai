"""Local process transport launcher. No plaintext input or recovery API."""
import json,secrets,socket,subprocess,sys
from .mpc import ROOT

def launch(directory,sid,bits,peer=True,mutate=None,worker='src.mpc_worker',timeout=30):
    s0,s1=socket.socketpair();attempt=secrets.token_hex(8); procs=[]
    if mutate: mutate(directory)
    if peer:
        for role,sock in [(0,s0),(1,s1)]:
            procs.append(subprocess.Popen([sys.executable,'-m',worker,str(role),str(directory),sid,str(bits),str(sock.fileno()),attempt],cwd=ROOT,pass_fds=(sock.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
        s0.close();s1.close()
        try:logs=[p.communicate(timeout=timeout) for p in procs]
        except subprocess.TimeoutExpired:
            for p in procs:
                if p.poll() is None:p.terminate()
            for p in procs:
                try:p.communicate(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.communicate()
            # Reserved batches remain burned even if SIGTERM bypasses finally.
            raise
        assert all(not err for out,err in logs), 'worker unexpected stderr'
        metrics=[json.loads((directory/('S'+str(role))/('metrics-'+attempt+'.json')).read_text()) for role in (0,1)]
    else:
        proc=subprocess.Popen([sys.executable,'-m',worker,'1',str(directory),sid,str(bits),str(s1.fileno()),attempt],cwd=ROOT,pass_fds=(s1.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        s1.close(); return proc,s0,attempt
    return attempt,metrics

