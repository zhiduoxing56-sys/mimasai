"""Independent verifier for exact signed public-count averages, not online code."""
import copy,json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import session,launch
from src.reference import Fixed,config
from src.data import cora
from src.numerical import training_reference

def main():
    summaries=[]
    for bits in (4,5,32):
        mod=1<<bits
        vals=list(range(-mod//2,mod//2)) if bits<32 else [-mod//2,-mod//2+1,-13,-12,-11,-1,0,1,11,12,13,mod//2-1]+[secrets.randbelow(mod)-mod//2 for _ in range(128)]
        counts=[1,2,3,5,7] if bits<32 else [1,2,3,5,7,31,255,256,2708]
        ops=[dict(type='average',count=len(vals),divisor=k,x=vals,expected=[v//k%mod for v in vals]) for k in counts]
        d,s,dealer=session(bits,ops);attempt,metrics=launch(d,s,bits,timeout=120)
        assert all(m['success'] and m['preprocessing']['consumed']==dealer['generated'] for m in metrics),[(m['error']) for m in metrics]
        own=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'] for r in (0,1)]
        assert all([(a+b)%mod for a,b in zip(own[0][i],own[1][i])]==op['expected'] for i,op in enumerate(ops))
        summaries.append(dict(bits=bits,checks=len(vals)*len(counts),session=s,bytes=sum(m['communication']['bytes_sent'] for m in metrics),rounds=metrics[0]['communication']['exchange_rounds']))
    # Non-power-of-two train count, same Cora16 graph, explicitly a protocol fixture.
    import random
    c=copy.deepcopy(config());c['fraction_bits']=c['training_reference']['fraction_bits'];c['training_reference']['loss_mode']='range_reduced';fx=Fixed(c);data=cora(node_count=16);n=16;f=len(data['feature_columns']);h=3;classes=7;rng=random.Random(c['data_experiment']['initialization_seed']);w=[fx.encode([[rng.gauss(0,.2) for _ in range(h)] for _ in range(f)]),fx.encode([[rng.gauss(0,.2) for _ in range(classes)] for _ in range(h)])];mask=[i in data['splits']['train'][:3] for i in range(n)];p=fx.encode(data['propagation']);x=fx.encode(data['features']);tr,_,_=training_reference(p,x,w,data['labels'],mask,c);flat=lambda a:[v for row in a for v in row];op=dict(type='train_step',dims=[n,f,h,classes],fraction=c['fraction_bits'],training_mask=mask,range_strategy='row_l1',loss_mode='range_reduced',x=flat(x),p=flat(p),y=flat(w[0])+flat(w[1]),labels=[fx.scale if j==data['labels'][i] else 0 for i in range(n) for j in range(classes)],expected=[]);d,s,dealer=session(32,[op]);a,m=launch(d,s,32,timeout=180);assert all(q['success'] for q in m),[q['error'] for q in m];own=[json.loads((d/f'S{r}/output-{a}.json').read_text())['shares'][0] for r in (0,1)];assert [(a+b)%(1<<32) for a,b in zip(*own)]==[v for values in tr.values() for v in values]
    out=Path('results/application/average.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(dict(status='PASS_EXACT_AVERAGE_AND_THREE_SAMPLE_TRAINING',averages=summaries,three_training_samples_fixture_session=s,actual_experiment_split_unchanged=True),indent=2)+'\n');print('PASS_EXACT_AVERAGE_AND_THREE_SAMPLE_TRAINING')
if __name__=='__main__':main()
