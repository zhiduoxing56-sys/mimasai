"""Existing signed-floor semantics with a guard on retained secret bits."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.final_he_compare import ISOLATED_ROOT
from verification.stage2 import verify,session,launch
from src.reference import config
from src.storage import record
from src.mpc import costs


def main():
    bits=32;fraction=config()['fraction_bits'];k=config()['mpc']['activation_range_bits']
    bound=1<<(k-1);mod=1<<bits
    values=[-bound*(1<<fraction),-1,0,1,(bound-1)*(1<<fraction)+(1<<fraction)-1]
    expected=[v//(1<<fraction)%mod for v in values]
    old=[dict(type='truncate',count=len(values),fraction=fraction,x=values,expected=expected),
         dict(type='range',count=len(values),k=k,use_previous=True,expected=[])]
    prior,_=verify(bits,old,'truncate_then_range')
    fused=[dict(type='truncate_checked',count=len(values),fraction=fraction,k=k,x=values,expected=expected)]
    current,_=verify(bits,fused,'fused_truncate_range')
    invalid=[bound*(1<<fraction)]
    directory,sid,_=session(bits,[dict(type='truncate_checked',count=1,fraction=fraction,k=k,x=invalid)])
    _,rejected=launch(directory,sid,bits)
    assert all(not row['success'] and row['error']=='RANGE_REJECTED' for row in rejected),rejected
    assert record(sid)['state']=='aborted'
    before=costs([{key:value for key,value in op.items() if key not in ('x','expected')} for op in old],bits)
    after=costs([{key:value for key,value in fused[0].items() if key not in ('x','expected')}],bits)
    evidence=dict(status='PASS_FUSED_SECRET_RANGE',valid_values_checked=len(values),rejected_session=sid,
                  invalid_range_rejected=True,old_rounds=prior['exchange_rounds'],fused_rounds=current['exchange_rounds'],
                  old_wire_bytes=prior['wire_bytes'],fused_wire_bytes=current['wire_bytes'],
                  old_boolean_materials=before['boolean'],fused_boolean_materials=after['boolean'],
                  output_semantics='signed floor and same batch range result')
    out=Path(__file__).resolve().parents[1]/'results/final-experiments/fused-range.json'
    out.write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))


if __name__=='__main__':main()
