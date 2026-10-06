"""Capacity fault fixture: reserve real batch, spawn native-like grandchild."""
import json,subprocess,sys,time
from pathlib import Path
from src.mpc import Materials
role,directory,sid,bits,fd,attempt=sys.argv[1:]
own=Path(directory)/('S'+role)
m=Materials(own/'preprocessing.json',int(role),sid,int(bits))
ready=own/'grandchild-ready.json'
child=subprocess.Popen([sys.executable,'-c',
    'import os,signal,time,sys;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.close(1);os.close(2);Path(sys.argv[1]).write_text("ready");time.sleep(60)',str(ready)],close_fds=True)
while not ready.exists():time.sleep(.005)
(own/'reserved-marker.json').write_text(json.dumps(dict(pid=child.pid)))
time.sleep(60)
