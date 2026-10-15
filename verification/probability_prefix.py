"""Actual MPC regression for bounded exact probability division."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.final_he_compare import ISOLATED_ROOT
from verification.stage2 import verify
from src.numerical import probability_reference
from src.reference import config
from src.operators import CostCounter,divide_unsigned


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rows',type=int,choices=(3,64),default=3);args=parser.parse_args()
    fraction=config()['probability_fraction_bits'];s=1<<fraction
    patterns=[[0]*7,[-2*s,-s,0,s,2*s,-3*s,3*s],[0,-8*s,-4*s,2*s,-2*s,5*s,-5*s]]
    rows=[patterns[i%len(patterns)] for i in range(args.rows)]
    expected,_=probability_reference(rows,fraction)
    result,_=verify(32,[dict(type='probability',count=args.rows*7,dims=[args.rows,7],fraction=fraction,
                             x=sum(rows,[]),expected=sum(expected,[]))],'bounded_probability_prefix')
    old=CostCounter(32);new=CostCounter(32);n=args.rows*7;nbits=2*fraction+1;dbits=fraction+(7).bit_length()
    divide_unsigned(old,[0]*n,[0]*n,nbits,dbits)
    divide_unsigned(new,[0]*n,[0]*n,nbits,dbits,skip_leading=fraction,denominator_lower_bound=s)
    evidence=dict(status='PASS_EXACT_PROBABILITY_PREFIX',session=result['session'],rows=args.rows,classes=7,
                  fixed_point_outputs_checked=n,actual_rounds=result['exchange_rounds'],
                  actual_operation_seconds=max(row['operations'][0]['elapsed_seconds'] for row in result['servers']),
                  old_division_boolean_materials=old.counts['boolean'],
                  optimized_division_boolean_materials=new.counts['boolean'],
                  actual_wire_bytes=result['wire_bytes'],numeric_semantics='bitwise identical to existing fixed-point reference')
    out=Path(__file__).resolve().parents[1]/f'results/final-experiments/probability-prefix-{args.rows}.json'
    out.write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))


if __name__=='__main__':main()
