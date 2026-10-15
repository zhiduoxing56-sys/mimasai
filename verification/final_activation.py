"""Fresh-material FSS comparison at two public comparison widths."""
import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.final_he_compare import OUT, ROOT  # isolated benchmark state
from verification.stage2 import verify
from src.storage import snapshot


def run(width, values):
    if width not in (10,32):
        raise ValueError('benchmark width')
    if snapshot(ROOT)['host_status'] != 'READABLE':
        raise RuntimeError('HOST_SPACE_UNKNOWN')
    result, (directory, _, _) = verify(32,[dict(type='fss_relu',count=len(values),
        k=width,x=values,expected=[max(0,v) for v in values])],f'final_activation_{width}')
    key_bytes=[];preprocessing_bytes=[]
    for role in (0,1):
        path=directory/f'S{role}/preprocessing.json'
        doc=json.loads(path.read_text());keys=doc['materials']['fss']
        key_bytes.append(sum(len(json.dumps(key,separators=(',',':')).encode()) for key in keys))
        preprocessing_bytes.append(path.stat().st_size)
    op=[m['operations'][0] for m in result['servers']]
    components=[dict(name=part['name'],worker_seconds=max(next(x for x in row['components']
        if x['name']==part['name'])['elapsed_seconds'] for row in op),
        wire_bytes=sum(next(x for x in row['components'] if x['name']==part['name'])['bytes_sent']
                       for row in op),rounds=part['rounds']) for part in op[0]['components']]
    return dict(status='PASS_EQUAL_TO_PLAINTEXT',comparison_width_bits=width,count=len(values),
        public_test_vector=values,
        session=result['session'],offline_seconds=result['dealer']['offline_wall_seconds'],
        keygen_seconds=result['dealer']['fss_keygen_seconds'],
        fss_key_bytes_per_role=key_bytes,
        serialized_preprocessing_bytes_per_role=preprocessing_bytes,
        online_worker_seconds=max(o['elapsed_seconds'] for o in op),
        online_wire_bytes=result['wire_bytes'],online_rounds=result['exchange_rounds'],
        online_operation_bytes=sum(o['bytes_sent'] for o in op),
        components=components,
        offline_generated=result['dealer']['generated'],
        counting='Key bytes are serialized per-role FSS entries; full preprocessing includes other material. No network distribution was executed, so distribution wire/time is unmeasured.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=32)
    parser.add_argument('--widths',type=int,nargs='+',default=[10,32]);args=parser.parse_args()
    if not 1<=args.count<=128:raise ValueError('count budget')
    if any(k not in (10,32) for k in args.widths):raise ValueError('width budget')
    # One vector is used unchanged for both widths, with both signs and bounds.
    fixed=[-511,-510,-1,0,1,509,510,511]
    values=(fixed+[secrets.randbelow(1024)-512 for _ in range(max(0,args.count-len(fixed)))])[:args.count]
    OUT.mkdir(parents=True,exist_ok=True)
    for width in args.widths:
        try:
            report=run(width,values)
            path=OUT/f'activation-k{width}-n{args.count}-{report["session"]}.json'
            path.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:report[k] for k in ('status','comparison_width_bits','count',
                'keygen_seconds','fss_key_bytes_per_role','online_worker_seconds',
                'online_wire_bytes','online_rounds')},ensure_ascii=False),flush=True)
        except BaseException as error:
            (OUT/f'activation-k{width}-n{args.count}-{secrets.token_hex(4)}.failed.json').write_text(json.dumps(dict(status='FAILED',
                width=width,error_type=type(error).__name__,reason=str(error)),indent=2)+'\n')
            raise


if __name__=='__main__':main()
