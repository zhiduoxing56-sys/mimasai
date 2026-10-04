"""Independent verifier of the scoped training f14 probability/f12 update bridge."""
import copy,json,math,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import verify,session,launch,ROOT
from src.reference import config,Fixed
from src.numerical import probability_reference,negative_log_reference,training_reference

def main():
 c=config();ft=c['training_reference']['fraction_bits'];pf=c['training_reference']['probability_fraction_bits'];s=1<<pf;runs=[]
 exp=probability_reference([[0,-8*s,-16*s,-24*s,-32*s,-40*s,-48*s]],pf)[1][0]['exponential'];assert min(exp)==8 and min(exp)*s//(7*s)>=1
 scores=[[0]*7,[32*s-4,-32*s,0,s,-s,8*s,-8*s],[-32*s]*7]
 prob,_=probability_reference(scores,pf)
 r,_=verify(32,[dict(type='probability',count=21,dims=[3,7],fraction=pf,x=sum(scores,[]),expected=sum(prob,[]))],'training_f14_probability');runs.append(r)
 q=[1,2,3,s//2-1,s//2,s//2+1,s-1,s]+[random.Random(20261005+i).randint(1,s) for i in range(128)]
 r,_=verify(32,[dict(type='negative_log',count=len(q),fraction=pf,x=q,expected=[negative_log_reference(v,pf) for v in q])],'training_f14_log');runs.append(r)
 # Integer floor composition, including negative updates, arbitrary sample counts.
 for count in (3,28):
  for v in range(-s,s+1):assert (v//4)//count==v//(4*count)
 vals=[-s,-s+1,-129,-128,-127,-1,0,1,127,128,129,s-1,s]
 r,_=verify(32,[dict(type='average',count=len(vals),divisor=28,x=vals,expected=[v//28%(1<<32) for v in vals]),dict(type='truncate',count=len(q),fraction=pf-ft,x=q,expected=[v//4 for v in q])],'training_mean_and_downscale');runs.append(r)
 cc=copy.deepcopy(c);cc['fraction_bits']=ft;cc['training_reference']['loss_mode']='range_reduced';fx=Fixed(cc);rng=random.Random(20261005)
 n,ff,h,cl=6,3,2,7;p=fx.encode([[float(i==j) for j in range(n)] for i in range(n)]);x=fx.encode([[rng.uniform(-.2,.2) for _ in range(ff)] for _ in range(n)]);w=[fx.encode([[rng.uniform(-.2,.2) for _ in range(h)] for _ in range(ff)]),fx.encode([[rng.uniform(-.2,.2) for _ in range(cl)] for _ in range(h)])];labels=list(range(n));mask=[i<3 for i in range(n)];trace,_,_=training_reference(p,x,w,labels,mask,cc)
 op=dict(type='train_step',dims=[n,ff,h,cl],fraction=ft,training_mask=mask,aggregation='dense',range_strategy='row_l1',loss_mode='range_reduced',x=sum(x,[]),p=sum(p,[]),y=sum(w[0],[])+sum(w[1],[]),labels=[fx.scale if j==i else 0 for i in labels for j in range(cl)],expected=[v for a in trace.values() for v in a]);r,_=verify(32,[op],'mixed_precision_training_three_samples');runs.append(r)
 d,sid,dealer=session(32,[dict(type='negative_log',count=1,fraction=pf,x=[0])]);attempt,m=launch(d,sid,32);assert all(not v['success'] for v in m) and all(not (d/f'S{r}/output-{attempt}.json').exists() for r in (0,1));_,replay=launch(d,sid,32);assert all(v['error']=='BATCH_ALREADY_RESERVED' for v in replay)
 errors=[abs(negative_log_reference(v,pf)/s+math.log(v/s)) for v in range(1,s+1)]
 out=ROOT/'results/representative';out.mkdir(exist_ok=True);(out/'precision.json').write_text(json.dumps(dict(status='PASS',training_fraction=ft,probability_fraction=pf,inference_probability_fraction=c['probability_fraction_bits'],minimum_exponential_units=8,seven_class_minimum_probability_units=1,log_all_positive_integer_reference_count=s,log_max_absolute_error=max(errors),runs=runs,zero_rejected=m,zero_replay=replay),indent=2)+'\n');print('PASS mixed training precision')
if __name__=='__main__':main()
