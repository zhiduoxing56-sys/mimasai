"""TEST ONLY: attempt a reference fixture read after live hello/material reserve."""
from src.mpc import Channel,ROOT
from src.mpc_worker import main
original=Channel.exchange
def exchange(self,op,kind,shape,values,dtype='u32',span=None):
    out=original(self,op,kind,shape,values,dtype,span)
    if kind=='hello':(ROOT/'verification/fixtures/gcn-reference.json').read_bytes()
    return out
Channel.exchange=exchange
if __name__=='__main__':raise SystemExit(main())
