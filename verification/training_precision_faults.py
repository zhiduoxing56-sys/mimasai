"""Fail-closed precision lifting and pre-lift label validation, independent verifier."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import ROOT,session,launch

def main():
 runs=[]
 for name,op in [('score_source_range',dict(type='precision_up',count=2,source_fraction=12,fraction=14,x=[0,32*4096])),('label_pre_lift_alias',dict(type='train_step',dims=[1,1,1,7],fraction=12,training_mask=[True],aggregation='dense',range_strategy='row_l1',loss_mode='range_reduced',x=[0],p=[4096],y=[0]*8,labels=[(1<<30)+4096]+[0]*6))]:
  d,s,dealer=session(32,[op]);attempt,m=launch(d,s,32);assert all(not x['success'] for x in m);assert all(not (d/f'S{r}/output-{attempt}.json').exists() for r in (0,1));_,restart=launch(d,s,32);assert all(x['error']=='BATCH_ALREADY_RESERVED' for x in restart);runs.append(dict(name=name,session=s,dealer=dealer,servers=m,restart=restart))
 (ROOT/'results/representative/precision-faults.json').write_text(json.dumps(dict(status='PASS',runs=runs),indent=2)+'\n');print('PASS precision fault burn')
if __name__=='__main__':main()
