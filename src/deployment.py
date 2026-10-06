"""Fixed local deployment bindings and bounded Unix IPC, no caller paths/argv."""
import json,os,pwd,socket,struct
from pathlib import Path
from .mpc import require,ProtocolError

BASE=Path('/var/lib/privacy-gnn')
CODE=Path('/opt/privacy-gnn/code')
RUN=Path('/run/privacy-gnn')
ROLES=('s0','s1','dealer','receiver','coordinator','page')
BROKER=RUN/'role-exec.sock'
PUBLIC_API=RUN/'public/coordinator.sock'
EXPERIMENT='a49152b33097752eaf81a7cba6d910a3'
LIMIT=65536

class RemoteError(ProtocolError):
    def __init__(self,code,stopped):super().__init__(code);self.stopped=stopped

def root(role):
    require(role in ROLES,'DEPLOY_ROLE')
    return BASE/'actors'/role
def identity(role):return pwd.getpwnam('pgnn-'+role)
def hexid(value,length=32):
    require(isinstance(value,str) and len(value)==length and all(c in '0123456789abcdef' for c in value),'DEPLOY_IDENTIFIER')
    return value
def policy():return json.loads((CODE/'config/deployment-public.json').read_text())
def atomic(path,value,mode=0o600):
    import secrets
    path=Path(path);temporary=path.with_name(path.name+'.pending-'+secrets.token_hex(8))
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,mode)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def exact(value,fields):require(isinstance(value,dict) and set(value)==set(fields),'DEPLOY_FIELDS')
def receive(sock):
    def read(count):
        parts=[]
        while count:
            chunk=sock.recv(count);require(bool(chunk),'IPC_EOF');parts.append(chunk);count-=len(chunk)
        return b''.join(parts)
    size=struct.unpack('!I',read(4))[0];require(0<size<=LIMIT,'IPC_SIZE')
    return json.loads(read(size))
def send(sock,value):
    data=json.dumps(value,separators=(',',':')).encode();require(len(data)<=LIMIT,'IPC_SIZE')
    sock.sendall(struct.pack('!I',len(data))+data)
def peer_uid(sock):return struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
def call(path,value,timeout=360):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout);sock.connect(str(path));send(sock,value);reply=receive(sock)
    if reply.get('ok') is not True:raise RemoteError(reply.get('error','ROLE_INTERFACE_FAILED'),reply.get('stopped',False))
    return reply['value']
def actor_environment(role):
    cfg=json.loads((CODE/'config/storage.json').read_text())
    return dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONPATH=str(CODE),PYTHONDONTWRITEBYTECODE='1',
        PGNN_ROOT=str(root(role)),PGNN_GATE_DIR=str(BASE/'gate'),WSL_DISTRO_NAME=cfg['host']['distro'])
