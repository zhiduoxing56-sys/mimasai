"""Linux process-group supervision. Pipe EOF is never termination evidence."""
import contextlib, os, signal, subprocess, threading, time
from pathlib import Path
from .mpc import ProtocolError, require

class StopUnconfirmed(ProtocolError):
    stopped = False

def members(group):
    live=[]
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            # comm may contain spaces or parentheses: split after its last ).
            fields=path.read_text().rsplit(')',1)[1].split()
            if int(fields[2])==group and fields[0] not in ('Z','X'):
                live.append(int(path.parent.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (OSError, ValueError, IndexError) as error:
            raise StopUnconfirmed('PROCESS_GROUP_INSPECTION_FAILED:'+str(error)) from error
    return live

@contextlib.contextmanager
def uninterrupted_stop():
    previous={}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT,signal.SIGTERM):
            previous[signum]=signal.signal(signum,signal.SIG_IGN)
    try:yield
    finally:
        for signum,handler in previous.items():signal.signal(signum,handler)

def stop(procs,grace=3):
    with uninterrupted_stop():
        signal_errors=[]
        for proc in procs:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            except OSError as error:signal_errors.append(str(error))
        deadline=time.monotonic()+grace
        try:
            while time.monotonic()<deadline:
                for proc in procs:proc.poll()
                if not any(members(proc.pid) for proc in procs):break
                time.sleep(.02)
        finally:
            # EOF, parent exit, or a failed /proc inspection must not suppress
            # this group-wide escalation. Inspection still gates completion.
            for proc in procs:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except OSError as error:signal_errors.append(str(error))
        deadline=time.monotonic()+3
        while True:
            for proc in procs:proc.poll()
            remaining={proc.pid:members(proc.pid) for proc in procs}
            if not any(remaining.values()):break
            if time.monotonic()>deadline:
                raise StopUnconfirmed('PROCESS_GROUP_STOP_UNCONFIRMED:'+str(remaining)+';signals:'+str(signal_errors))
            time.sleep(.02)
        for proc in procs:
            try:proc.communicate(timeout=.5)
            except subprocess.TimeoutExpired:
                # All group members are stopped. A pipe held outside the group
                # cannot be used as a completion criterion; close our endpoints.
                for pipe in (proc.stdout,proc.stderr):
                    if pipe:pipe.close()
        return dict(stopped=True,groups=[proc.pid for proc in procs],criterion='no non-zombie process-group members in /proc')

def quiescent(procs):
    require(not any(members(proc.pid) for proc in procs),'WORKER_DESCENDANT_SURVIVED')
    return dict(stopped=True,groups=[proc.pid for proc in procs],criterion='no non-zombie process-group members in /proc')

def run(args,*,cwd,timeout=300):
    proc=subprocess.Popen(args,cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,start_new_session=True,close_fds=True)
    try:
        out,err=proc.communicate(timeout=timeout)
        quiescent([proc])
        if proc.returncode:raise subprocess.CalledProcessError(proc.returncode,args,out,err)
        return subprocess.CompletedProcess(args,proc.returncode,out,err)
    except BaseException:
        stop([proc]);raise
