"""Lifecycle fixture: successful checkpoint write, no protocol computation."""
import sys
from pathlib import Path
from src.mpc import Materials,private_write
role,directory,sid,bits,fd,attempt=sys.argv[1:];own=Path(directory)/('S'+role)
m=Materials(own/'preprocessing.json',int(role),sid,int(bits));m.finish(True)
private_write(own/('output-'+attempt+'.json'),dict(checkpoint_fixture=True))
private_write(own/('metrics-'+attempt+'.json'),dict(success=True,error=None))
