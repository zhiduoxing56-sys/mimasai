"""Exact non-power-of-two secret range guards, boundaries and durable rejection."""
import json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import session,launch

def check(bits,values,radius):
    bound=dict(bits=(radius-1).bit_length()+1,radius=radius);op=dict(type='range',count=len(values),k=bound,x=[v%(1<<bits) for v in values],expected=[]);d,s,dealer=session(bits,[op]);a,m=launch(d,s,bits,timeout=60);valid=all(-radius<=v<radius for v in values)
    assert all(q['success']==valid for q in m),[q['error'] for q in m]
    if valid:assert all(q['preprocessing']['consumed']==dealer['generated'] for q in m)
    else:
        assert all(q['error']=='RANGE_REJECTED' for q in m);assert not any((d/f'S{r}/output-{a}.json').exists() for r in (0,1));_,again=launch(d,s,bits);assert all(q['error']=='BATCH_ALREADY_RESERVED' for q in again)
    return dict(bits=bits,public_radius=radius,values=len(values),valid=valid,session=s,wire_bytes=sum(q['communication']['bytes_sent'] for q in m),rounds=m[0]['communication']['exchange_rounds'])

def main():
    tests=[check(4,[v],3) for v in range(-8,8)];r=24*(1<<12)
    tests+=[check(32,[-r,-r+1,-1,0,1,r-1]+[secrets.randbelow(2*r)-r for _ in range(128)],r)]
    tests+=[check(32,[-r,v,0],r) for v in (r,-r-1,-(1<<31),(1<<31)-1)]
    out=Path('results/application/interval.json');out.parent.mkdir(exist_ok=True,parents=True);out.write_text(json.dumps(dict(status='PASS_EXACT_NONPOWER_SECRET_INTERVAL',cases=tests,leakage='one batch-valid flag; no signs or failure positions',proof='signed x>=-radius AND radius-1>=x; exact full-ring signed comparisons; L1 cap uses actual radius, not enclosing power of two'),indent=2)+'\n');print('PASS_EXACT_NONPOWER_SECRET_INTERVAL')
if __name__=='__main__':main()
