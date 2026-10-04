"""TEST ONLY: disconnect after a real masked ring-product opening."""
from src.mpc import Channel,ProtocolError
from src.mpc_worker import main
original=Channel.exchange
def exchange(self,op,kind,shape,values,dtype='u32',span=None):
 result=original(self,op,kind,shape,values,dtype,span)
 if self.role==0 and kind=='rlwe_beaver_masks':self.sock.close();raise ProtocolError('DISCONNECTED')
 return result
Channel.exchange=exchange
if __name__=='__main__':raise SystemExit(main())
