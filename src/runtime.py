"""Local launcher with capacity monitoring and durable abort. No recovery API."""
import json, os, secrets, signal, socket, subprocess, sys, threading, time
from pathlib import Path
from .mpc import ROOT, require, ProtocolError
from .storage import lease,record,transition,Guard,burn,abort_signals

def stop(procs):
    # Kill entire groups, including native HE grandchildren, before releasing
    # the session lease. A child cannot continue filling the disk after abort.
    for proc in procs:
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    for proc in procs:
        try:proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.communicate()

def launch(directory,sid,bits,peer=True,mutate=None,worker='src.mpc_worker',timeout=30,defer_completion=False):
    directory=Path(directory)
    # One-sided fault workers still reserve in their role ledger. They cannot
    # be treated as terminal until their caller terminates them; never clean.
    if not peer:
        context=lease(sid);context.__enter__()
        try:
            entry=record(sid);require(entry and entry['state']=='ready','SESSION_STATE_REJECTED')
            guard=Guard(directory,sid,entry['budget']);guard.check(force=True)
            transition(sid,{'ready'},'running','one-sided supervised fault worker')
            s0,s1=socket.socketpair();attempt=secrets.token_hex(8)
            proc=subprocess.Popen([sys.executable,'-m',worker,'1',str(directory),sid,str(bits),str(s1.fileno()),attempt],cwd=ROOT,pass_fds=(s1.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            s1.close()
        except BaseException as error:
            if record(sid) and record(sid)['state'] in ('ready','running'):burn(sid,str(error))
            context.__exit__(None,None,None);raise
        def monitor():
            detail='one-sided worker exited; batch burned'
            try:
                deadline=time.monotonic()+timeout
                while proc.poll() is None:
                    guard.check()
                    if time.monotonic()>deadline:raise ProtocolError('ONLINE_TIMEOUT')
                    time.sleep(.05)
            except BaseException as error:
                detail=str(error)
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    proc.wait()
            finally:
                try:burn(sid,detail)
                finally:context.__exit__(None,None,None)
        proc.storage_monitor=threading.Thread(target=monitor,daemon=False)
        proc.storage_monitor.start()
        return proc,s0,attempt
    with lease(sid),abort_signals():
        entry=record(sid);require(entry and entry['state']=='ready','SESSION_STATE_REJECTED')
        procs=[];s0,s1=socket.socketpair();attempt=secrets.token_hex(8)
        try:
            guard=Guard(directory,sid,entry['budget']);guard.check(force=True)
            transition(sid,{'ready'},'running')
            if mutate:mutate(directory)
            for role,sock in ((0,s0),(1,s1)):
                procs.append(subprocess.Popen([sys.executable,'-m',worker,str(role),str(directory),sid,str(bits),str(sock.fileno()),attempt],cwd=ROOT,pass_fds=(sock.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True))
            s0.close();s1.close();deadline=time.monotonic()+timeout
            while any(proc.poll() is None for proc in procs):
                guard.check()
                if time.monotonic()>deadline:raise ProtocolError('ONLINE_TIMEOUT')
                # Drain pipes so a worker cannot block on an output buffer.
                for proc in procs:
                    try:proc.communicate(timeout=.05)
                    except subprocess.TimeoutExpired:pass
            logs=[proc.communicate() for proc in procs]
            require(all(not err for out,err in logs),'WORKER_STDERR')
            metrics=[json.loads((directory/f'S{role}'/f'metrics-{attempt}.json').read_text()) for role in (0,1)]
            for proc,metric in zip(procs,metrics):
                if proc.returncode!=0 and metric['success']:
                    metric['success']=False;metric['error']='WORKER_EXIT_'+str(proc.returncode)
            if all(m['success'] for m in metrics):
                if not defer_completion:transition(sid,{'running'},'completed')
            else:burn(sid,'worker failure')
            return attempt,metrics
        except BaseException as error:
            stop(procs);burn(sid,str(error));raise
        finally:s0.close();s1.close()
