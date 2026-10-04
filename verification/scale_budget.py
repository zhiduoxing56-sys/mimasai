"""Public planning and owner-side data bounds. Predictions are not measurements."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import config,Fixed,transpose
from src.mpc import costs

def main():
 c=config();cc=dict(c,fraction_bits=c['training_reference']['fraction_bits']);fx=Fixed(cc);rows=[]
 for n in (16,32,64):
  d=cora(node_count=n);p=fx.encode(d['propagation']);x=fx.encode(d['features']);f=len(x[0]);h=c['model_reference']['hidden_width'];classes=len(d['label_names']);op=dict(type='train_step',dims=[n,f,h,classes],fraction=cc['fraction_bits'],training_mask=[i in d['splits']['train'] for i in range(n)],aggregation='dense',loss_mode='range_reduced',range_strategy='row_l1');budget=costs([op],32);elements=max(n*f*h,n*n*classes);rows.append(dict(nodes=n,features=f,classes=classes,max_P_row_l1=max(map(sum,p)),max_X_row_l1=max(map(sum,x)),max_X_transpose_row_l1=max(map(sum,transpose(x))),state_product_l1_cap=((1<<31)-1)//(1<<(cc['fraction_bits']+c['range_policy']['operand_bound_exponents']['state'])),materials_per_step=budget,largest_arithmetic_mask_payload_bytes=elements*8,public_frame_limit=c['mpc']['max_frame_bytes'],frame_payload_fits_with_header_margin=elements*8+4096<c['mpc']['max_frame_bytes']))
 # Worst-case clipped exponential is a public algorithm calculation, not opened
 # private data. Every probability is >= floor(Emin/C).
 precision=[]
 for f in (12,14):
  s=1<<f;v=-s//2;e=s+v+(v*v//s)//2
  for _ in range(c['approximation']['exp_halving_bits']):e=e*e//s
  precision.append(dict(fraction=f,minimum_exponential_units=e,classes=7,probability_unit_lower_bound=e//7,largest_exp_product=s*s,signed32_product_safe=s*s<1<<31,protocol_status='current f12 probability and log' if f==12 else 'numeric candidate only; log currently capped at f12; mixed precision training not implemented'))
 r=dict(status='PUBLIC_BUDGET_AND_NUMERIC_CANDIDATES_ONLY',scales=rows,probability_precision=precision,limitations=['Range observations are owner-side; online guard remains mandatory','64-node numbers are planned, not an executed secure experiment','Full Cora dense first transform alone has 2708*1432*3*8 bytes, beyond the current 4 MiB frame','Wider ring requires protected conversion; blockwise floor changes semantics'])
 Path('results/real-data/scale-budget.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
