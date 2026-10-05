"""Authorized evaluation of existing checkpoints. No server input is changed."""
import argparse,copy,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import config,Fixed,ROOT
from src.data import cora
from src.metrics import evaluate
from src.numerical import probability_reference

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',default=str(ROOT/'results/real-data-64/reference.json'));parser.add_argument('--output',default=str(ROOT/'results/representative/old-checkpoints.json'));args=parser.parse_args();c=config();r=json.loads(Path(args.report).read_text());d=cora(node_count=r['dimensions'][0],sampling=r['data'].get('sampling','fixed_bfs'),seed=r['data'].get('sampling_seed'));pf=r.get('probability_fraction_bits',c['training_reference']['fraction_bits']);cc=copy.deepcopy(c);cc['fraction_bits']=c['training_reference']['fraction_bits'];fx=Fixed(cc);f,h,k=r['dimensions'][1:];rng=random.Random(r.get('initialization_seed',c['data_experiment']['initialization_seed']));w=[[[rng.gauss(0,.2) for _ in range(h)] for _ in range(f)],[[rng.gauss(0,.2) for _ in range(k)] for _ in range(h)]];initial=[v for layer in w for row in fx.encode(layer) for v in row];records=[]
    for iteration in sorted({0,1,*[v for v in (16,32,64,96,128,160,320) if v<=len(r['secure_training'])],len(r['secure_training'])}):
        if iteration==0:values=initial
        else:
            step=r['secure_training'][iteration-1];path=Path(step['directory']);count=f*h+h*k;shares=[json.loads((path/f'S{role}/output-{step["attempt"]}.json').read_text())['shares'][0][-count:] for role in (0,1)];values=[(a+b)%(1<<32) for a,b in zip(*shares)]
        weights=[ [values[i*h:(i+1)*h] for i in range(f)], [values[f*h+i*k:f*h+(i+1)*k] for i in range(h)]];tr=fx.forward(fx.encode(d['propagation']),fx.encode(d['features']),weights,'transform_then_aggregate');prob,_=probability_reference([[fx.signed(v)*(1<<(pf-(fx.scale.bit_length()-1))) for v in row] for row in tr['logits']],pf);metrics=evaluate(d,[[v/(1<<pf) for v in row] for row in prob]);records.append(dict(iteration=iteration,metrics=metrics));print(iteration,{name:(v['accuracy'],v['macro_f1'],v['prediction_counts']) for name,v in metrics.items()})
    out=ROOT/'results/representative';out.mkdir(exist_ok=True);from src.application import write as private_write
    private=ROOT/'build/representative/V';private.mkdir(parents=True,exist_ok=True,mode=0o700);private_write(private/Path(args.output).name,dict(scope='Authorized independent evaluation only; no online input or recipient changes',records=records))
    aggregate=[dict(iteration=q['iteration'],metrics={name:{k:v for k,v in m.items() if k!='nodes'} for name,m in q['metrics'].items()}) for q in records];private_write(Path(args.output),dict(scope='Authorized aggregate evaluation; per-node predictions restricted to build/representative/V',records=aggregate))
if __name__=='__main__':main()
