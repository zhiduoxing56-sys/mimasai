"""Exact Boolean wire packing and noncanonical-padding rejection."""
import json,secrets,socket,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import Channel,ProtocolError,settings,WIRE_ENCODING


def main():
    lengths=(0,1,7,8,9,127,1025)
    for n in lengths:
        sender,receiver=socket.socketpair()
        try:
            values=[secrets.randbits(1) for _ in range(n)]
            channel=Channel(receiver,1,secrets.token_hex(16),settings()['mpc'])
            frame,header=channel.frame(0,'packed_bits',[n],values,'bit',None)
            assert header['wire_encoding']==WIRE_ENCODING and header['payload_length']==(n+7)//8
            sender.sendall(frame);assert channel.receive(header)==values
            if n%8:
                bad=bytearray(frame);bad[-1]|=1<<(n%8)
                sender.sendall(bad)
                try:channel.receive(header)
                except ProtocolError as error:assert error.code=='PAYLOAD_BIT_PADDING'
                else:raise AssertionError('noncanonical bit padding accepted')
        finally:sender.close();receiver.close()
    result=dict(status='PASS_BITPACKED_WIRE',lengths=lengths,padding_rejected=True)
    out=Path(__file__).resolve().parents[1]/'results/final-experiments/bitpacked-channel.json'
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
