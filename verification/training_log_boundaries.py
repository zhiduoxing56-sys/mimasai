"""Supplemental new-f14 leader transitions and maximum-error point; no old tests repeated."""
import json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import verify,ROOT
from src.numerical import negative_log_reference

def main():
 f=14;s=1<<f;old=set([1,2,3,s//2-1,s//2,s//2+1,s-1,s]+[random.Random(20261005+i).randint(1,s) for i in range(128)]);values=sorted(({(1<<j)+d for j in range(f+1) for d in (-1,0,1)}|{8211})-old);values=[q for q in values if 1<=q<=s];r,_=verify(32,[dict(type='negative_log',count=len(values),fraction=f,x=values,expected=[negative_log_reference(q,f) for q in values])],'new_f14_leading_bit_transitions');(ROOT/'results/representative/log-boundaries.json').write_text(json.dumps(dict(status='PASS',new_checks=len(values),values=values,run=r),indent=2)+'\n');print('PASS',len(values))
if __name__=='__main__':main()
