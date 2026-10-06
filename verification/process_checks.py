"""Short adversarial termination fixtures; no training or model access."""
import json,os,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT
from src.processes import stop,members,run,StopUnconfirmed
from unittest.mock import patch

def main():
    out=ROOT/'results/lifecycle';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'build/storage-tests') as folder:
        marker=Path(folder)/'pid'
        child='import os,signal,time,sys;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.close(1);os.close(2);Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(60)'
        parent='import subprocess,sys,time;from pathlib import Path;subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]],close_fds=True);\nwhile not Path(sys.argv[2]).exists():time.sleep(.005)\n'
        proc=subprocess.Popen([sys.executable,'-c',parent,child,str(marker)],start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,close_fds=True)
        try:
            proc.communicate(timeout=3)
            pid=int(marker.read_text());assert proc.returncode==0 and pid in members(proc.pid)
            started=time.monotonic();proof=stop([proc],grace=.2)
            elapsed=time.monotonic()-started
            assert not members(proc.pid) and elapsed>=.2
        finally:stop([proc],grace=0)
        marker.unlink()
        interrupt_parent=parent+'time.sleep(60)'
        def interrupt():
            deadline=time.monotonic()+3
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.005)
            os.kill(os.getpid(),signal.SIGINT)
        t=threading.Thread(target=interrupt);t.start()
        try:run([sys.executable,'-c',interrupt_parent,child,str(marker)],cwd=ROOT,timeout=5)
        except KeyboardInterrupt:pass
        else:raise AssertionError('interrupt missing')
        t.join(timeout=5)
        pid=int(marker.read_text());stat=Path(f'/proc/{pid}/stat')
        assert not stat.exists() or stat.read_text().rsplit(')',1)[1].split()[0] in ('Z','X')
        ready=Path(folder)/'inspection-ready'
        proc=subprocess.Popen([sys.executable,'-c','import signal,time,sys;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path(sys.argv[1]).write_text("ready");time.sleep(60)',str(ready)],start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+3
            while not ready.exists() and time.monotonic()<deadline:time.sleep(.005)
            assert ready.exists()
            with patch('src.processes.members',side_effect=StopUnconfirmed('injected inspection failure')):
                try:stop([proc],grace=.2)
                except StopUnconfirmed:pass
                else:raise AssertionError('unconfirmed stop reported complete')
            proc.wait(timeout=2)
            assert proc.returncode==-signal.SIGKILL and not members(proc.pid)
        finally:stop([proc],grace=0)
    result=dict(status='PASS_CHANGED_PROCESS_GROUPS',closed_pipes_and_parent_exit_observed=True,
        resistant_grandchild_force_killed=True,grace_seconds=.2,elapsed_seconds=elapsed,proof=proof,
        interrupted_helper_group_stopped=True,inspection_failure_still_sends_kill_and_rejects_completion=True,training_executed=False)
    (out/'process-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
