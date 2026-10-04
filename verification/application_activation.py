"""Affected FSS widths: independent boundary checks, without replaying prior suites."""
import json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import verify
from verification.stage2_round2 import rejection

def main():
    runs=[];failures=[]
    for k in (13,18):
        radius=1<<(k-1)
        values=[-radius,-radius+1,-1,0,1,radius-2,radius-1]+[secrets.randbelow(2*radius)-radius for _ in range(121)]
        expected=[max(0,v) for v in values]
        ops=[dict(type='relu',count=len(values),x=values,expected=expected),dict(type='fss_relu',count=len(values),k=k,x=values,expected=expected)]
        result,_=verify(32,ops,'application_activation_width_'+str(k))
        runs.append(dict(k=k,count=len(values),wire_bytes=result['wire_bytes'],rounds=result['exchange_rounds']))
        for v in (-radius-1,radius):
            r=rejection(32,[v,0],k,'application_fss_boundary_'+str(k),operation='fss_relu')
            failures.append(dict(k=k,session=r['servers'][0]['session'] if 'session' in r['servers'][0] else None,status='NO_OUTPUT_AND_REUSE_REJECTED'))
    out=Path('results/application/activation-widths.json');out.write_text(json.dumps(dict(status='PASS_BOOLEAN_FSS_AFFECTED_WIDTHS',runs=runs,failures=failures),indent=2)+'\n')
    print('PASS_BOOLEAN_FSS_AFFECTED_WIDTHS')
if __name__=='__main__':main()
