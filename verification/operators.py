"""Independent process verification of prefix compare/division/probability/gather."""
import json,math,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import verify,session,launch,C,ROOT
from src.numerical import probability_reference
OUT=ROOT/'results/continuation';OUT.mkdir(exist_ok=True)
def main():
 results=[]
 # Complete small ring comparison, including signed extrema and wraparound pairs.
 for bits in (3,4,5):
  mod=1<<bits;xx=[a for a in range(mod) for b in range(mod)];yy=[b for a in range(mod) for b in range(mod)];sg=lambda v:v if v<mod//2 else v-mod
  r,_=verify(bits,[dict(type='compare',count=len(xx),x=xx,y=yy,expected=[int(sg(a)>=sg(b)) for a,b in zip(xx,yy)])],f'compare_all_{bits}');results.append(r)
 vals=[-2**31,-2**31+1,-1,0,1,2**31-2,2**31-1]+[secrets.randbelow(2**32)-2**31 for _ in range(64)]
 xx=[a for a in vals[:7] for b in vals[:7]]+vals;yy=[b for a in vals[:7] for b in vals[:7]]+list(reversed(vals));r,_=verify(32,[dict(type='compare',count=len(xx),x=xx,y=yy,expected=[int(a>=b) for a,b in zip(xx,yy)])],'compare_ring32');results.append(r)
 # All numerator/divisor combinations in a small domain, actual full32 circuits.
 xx=[a for a in range(32) for b in range(1,16)];yy=[b for a in range(32) for b in range(1,16)]
 r,_=verify(32,[dict(type='divide',count=len(xx),nbits=5,dbits=4,x=xx,y=yy,expected=[a//b for a,b in zip(xx,yy)])],'division_exhaustive_5_4');results.append(r)
 probs=[]
 for f in (7,12):
  s=1<<f;rows=[[0,0],[s,-s],[-8*s,8*s],[16*s-1,-16*s],[0,-8*s-1]]+[[secrets.randbelow(16*s)-8*s for _ in range(2)] for _ in range(16)]
  expected,_=probability_reference(rows,f);r,_=verify(32,[dict(type='probability',count=2*len(rows),dims=[len(rows),2],fraction=f,x=[v for row in rows for v in row],expected=[v for row in expected for v in row])],f'probability_f{f}');results.append(r)
  high=[[1/(1+math.exp((row[1]-row[0])/s)),1/(1+math.exp((row[0]-row[1])/s))] for row in rows]
  probs.append(dict(fraction=f,max_probability_error=max(abs(a/s-b) for rr,hh in zip(expected,high) for a,b in zip(rr,hh)),sum_range=[min(sum(row)/s for row in expected),max(sum(row)/s for row in expected)],classification_equal=all(row.index(max(row))==highrow.index(max(highrow)) for row,highrow in zip(expected,high))))
 array=[[5,-8],[2**31-1,-2**31],[-1,0],[7,9],[111,222]];ids=[0,4,2,3,1,0]
 r,_=verify(32,[dict(type='gather',count=len(ids),dims=[len(array),2],x=ids,y=[v for row in array for v in row],expected=[v for i in ids for v in array[i]])],'secret_index_scan');results.append(r)
 fails=[]
 for name,op,code in [('zero_denominator',dict(type='divide',count=2,nbits=5,dbits=4,x=[3,0],y=[1,0],expected=[]),'DIVISOR_NOT_POSITIVE'),('invalid_index',dict(type='gather',count=3,dims=[5,2],x=[0,5,-1],y=[v for row in array for v in row],expected=[]),'INDEX_RANGE_REJECTED'),('operand_range',dict(type='bounded_matmul',dims=[1,1,1],fraction=7,bounds=[9,10],x=[256],y=[128],expected=[]),'RANGE_REJECTED')]:
  d,s,_=session(32,[op]);attempt,m=launch(d,s,32);assert not any(x['success'] for x in m) and any(x['error']==code for x in m),(name,m);assert not any((d/f'S{r}/output-{attempt}.json').exists() for r in (0,1));_,restart=launch(d,s,32);assert all(x['error']=='BATCH_ALREADY_RESERVED' for x in restart);fails.append(dict(name=name,errors=[x['error'] for x in m]))
 report=dict(status='PASS_SECRET_OPERATOR_CIRCUITS',runs=results,probability=probs,failures=fails);(OUT/'operators.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],checks=sum(x['checks'] for x in results),probability=probs),indent=2))
if __name__=='__main__':main()
