"""TEST ONLY: close the real transport after full masked ciphertext exchange."""
import sys
from src.mpc import Channel, ProtocolError
from src.mpc_worker import main
original=Channel.exchange
def exchange(self,op,kind,shape,values,dtype='u32',span=None):
    result=original(self,op,kind,shape,values,dtype,span)
    if self.role==0 and kind=='he_masked_ciphertexts':
        self.sock.close()
        raise ProtocolError('DISCONNECTED')
    return result
Channel.exchange=exchange
if __name__=='__main__':raise SystemExit(main())
