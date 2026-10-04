"""Independent processes: tighter dot budget, exact arithmetic, durable failure."""
import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import Fixed,config
from verification.stage2 import session,launch,verify,ROOT

def main():
 cc=config();cc['fraction_bits']=12;fx=Fixed(cc);n=16
 # Old 16 * 8192 * 32768 >= 2^31, actual sparse row has L1=4096.
 a=[[4096 if i==j else 0 for j in range(n)] for i in range(2)];b=[[(-1 if j%2 else 1)*(20000+j)] for j in range(n)];expected=fx.mul(a,[[v%fx.mod for v in row] for row in b],'budget dot');op=dict(type='bounded_matmul',count=2,dims=[2,n,1],fraction=12,bounds=[14,16],range_strategy='row_l1',x=[v for row in a for v in row],y=[v%fx.mod for row in b for v in row],expected=[v for row in expected for v in row]);extended=dict(op,bounds=[14,17],y=[35000+j for j in range(n)],expected=[35000,35001]);positive,completed=verify(32,[op,extended],'row_l1_accept_dimension_reject')
 d,s,bits=completed;_,restart=launch(d,s,bits);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in restart)
 # Distinguish conservative rejection of cancelling sums from true overflow.
 rejected=[]
 for name,values in [('cancellation',[32767 if j%2 else -32767 for j in range(n)]),('true_partial_overflow',[32767]*n)]:
  total=0;maxpartial=0
  for v in values:total+=8191*v;maxpartial=max(maxpartial,abs(total))
  bad=dict(op,x=[8191]*32,y=[v%fx.mod for v in values],expected=[])
  d,s,dealer=session(32,[bad]);attempt,metrics=launch(d,s,32,timeout=60)
  assert all(m['error']=='DOT_L1_BOUND_REJECTED' for m in metrics)
  assert not any((d/f'S{r}/output-{attempt}.json').exists() for r in (0,1))
  _,replay=launch(d,s,32);assert all(m['error']=='BATCH_ALREADY_RESERVED' for m in replay)
  rejected.append(dict(name=name,true_max_abs_partial_sum=maxpartial,true_signed32_safe=maxpartial<1<<31,errors=[m['error'] for m in metrics],restart_errors=[m['error'] for m in replay]))
 assert rejected[0]['true_signed32_safe'] and not rejected[1]['true_signed32_safe']
 spans=[]
 for role in (0,1):
  db=sqlite3.connect(ROOT/f'state/mpc/S{role}-ledger.sqlite');rows=db.execute('SELECT kind,start,count FROM consumption_spans WHERE batch=? ORDER BY kind,start',(positive['dealer']['batch'],)).fetchall();end={}
  for kind,start,count in rows:assert start==end.get(kind,0);end[kind]=start+count
  assert end=={k:v for k,v in positive['dealer']['generated'].items() if v};spans.append(len(rows));db.close()
 result=dict(status='PASS_ROW_L1_SAFE_ACCEPT_CONSERVATIVE_AND_OVERFLOW_REJECTIONS',positive=positive,rejections=rejected,span_records=spans,proof='sum abs(Arow)*Bmax < 2^31 bounds every product and every partial sum; prechecked operand ranges and public no-wrap sum budget',leakage='One all-rows-valid batch bit, not norms, positions, signs or values',limitations='Conservative Bmax may still reject safe cancelling dot products; not a generic unlimited ring')
 out=ROOT/'results/real-data/range-budget.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
