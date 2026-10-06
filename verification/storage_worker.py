"""Capacity fault fixture: reserve real batch, spawn native-like grandchild."""
import json,subprocess,sys,time
from pathlib import Path
from src.mpc import Materials
role,directory,sid,bits,fd,attempt=sys.argv[1:]
own=Path(directory)/('S'+role)
m=Materials(own/'preprocessing.json',int(role),sid,int(bits))
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
(own/'reserved-marker.json').write_text(json.dumps(dict(pid=child.pid)))
time.sleep(60)
