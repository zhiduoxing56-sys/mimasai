"""Local launcher with capacity monitoring and durable abort. No recovery API."""
import contextlib, json, secrets, socket, subprocess, sys, threading, time
from pathlib import Path
from .mpc import ROOT, require, ProtocolError
from .storage import lease,workflow_lease,record,transition,Guard,burn,abort_signals

from .processes import stop,quiescent,StopUnconfirmed
from .storage import event

def launch(directory,sid,bits,peer=True,mutate=None,worker='src.mpc_worker',timeout=30,defer_completion=False):
    directory=Path(directory)
    # One-sided fault workers still reserve in their role ledger. They cannot
    # be treated as terminal until their caller terminates them; never clean.
    if not peer:
        context=contextlib.ExitStack();context.__enter__()
        proc=None;s0=s1=None;accepted=False
        try:
            context.enter_context(lease(sid,suffix='.workflow.lock'))
            context.enter_context(lease(sid))
            entry=record(sid);require(entry and entry['state'] in ('ready','preparing'),'SESSION_STATE_REJECTED')
            accepted=True
            guard=Guard(directory,sid,entry['budget']);guard.check(force=True)
            transition(sid,{'ready','preparing'},'running','one-sided supervised fault worker')
            s0,s1=socket.socketpair();attempt=secrets.token_hex(8)
            proc=subprocess.Popen([sys.executable,'-m',worker,'1',str(directory),sid,str(bits),str(s1.fileno()),attempt],cwd=ROOT,pass_fds=(s1.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,close_fds=True)
            s1.close()
        except BaseException as error:
            confirmed=False
            try:
                proof=stop([proc] if proc else []);confirmed=True
                if accepted:event(sid,'one_sided_setup_stop',proof=proof)
            finally:
                try:
                    if accepted:burn(sid,str(error),stopped=confirmed)
                finally:
                    for sock in (s0,s1):
                        if sock:sock.close()
                    context.__exit__(None,None,None)
            raise
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
            finally:
                confirmed=False
                try:
                    proof=stop([proc]);confirmed=True;event(sid,'backend_stop',proof=proof)
                finally:
                    try:burn(sid,detail,stopped=confirmed)
                    finally:context.__exit__(None,None,None)
        proc.storage_monitor=threading.Thread(target=monitor,daemon=False)
        try:proc.storage_monitor.start()
        except BaseException as error:
            confirmed=False
            try:
                proof=stop([proc]);confirmed=True;event(sid,'one_sided_monitor_start_stop',proof=proof)
            finally:
                try:burn(sid,str(error),stopped=confirmed)
                finally:s0.close();context.__exit__(None,None,None)
            raise
        return proc,s0,attempt
    with workflow_lease(sid),lease(sid),abort_signals():
        entry=record(sid);require(entry and entry['state'] in ('ready','preparing'),'SESSION_STATE_REJECTED')
        procs=[];s0,s1=socket.socketpair();attempt=secrets.token_hex(8)
        try:
            guard=Guard(directory,sid,entry['budget']);guard.check(force=True)
            transition(sid,{'ready','preparing'},'running')
            if mutate:mutate(directory)
            for role,sock in ((0,s0),(1,s1)):
                procs.append(subprocess.Popen([sys.executable,'-m',worker,str(role),str(directory),sid,str(bits),str(sock.fileno()),attempt],cwd=ROOT,pass_fds=(sock.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,close_fds=True))
            s0.close();s1.close();deadline=time.monotonic()+timeout
            while any(proc.poll() is None for proc in procs):
                guard.check()
                if time.monotonic()>deadline:raise ProtocolError('ONLINE_TIMEOUT')
                # Drain pipes so a worker cannot block on an output buffer.
                for proc in procs:
                    try:proc.communicate(timeout=.05)
                    except subprocess.TimeoutExpired:pass
            quiescent(procs)
            logs=[proc.communicate(timeout=.5) for proc in procs]
            event(sid,'backend_stopped',proof=quiescent(procs))
            require(all(not err for out,err in logs),'WORKER_STDERR')
            metrics=[json.loads((directory/f'S{role}'/f'metrics-{attempt}.json').read_text()) for role in (0,1)]
            for proc,metric in zip(procs,metrics):
                if proc.returncode!=0 and metric['success']:
                    metric['success']=False;metric['error']='WORKER_EXIT_'+str(proc.returncode)
            if all(m['success'] for m in metrics):
                if not defer_completion:transition(sid,{'running'},'completed')
            else:burn(sid,'worker failure',stopped=True)
            return attempt,metrics
        except BaseException as error:
            confirmed=False
            try:
                proof=stop(procs);confirmed=True;event(sid,'backend_stop',proof=proof)
            finally:burn(sid,str(error),stopped=confirmed)
            raise
        finally:s0.close();s1.close()
