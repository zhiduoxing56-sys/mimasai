"""Independent wide-integer references for approximate probability and training."""
import math
from .reference import Fixed,config,transpose

def probability_reference(scores,fraction):
    s=1<<fraction;result=[];traces=[];approx=config()['approximation'];halving=approx['exp_halving_bits']
    for row in scores:
        m=max(row);d=[max(v-m,-approx['exp_clip_real']*s) for v in row];v=[x//(1<<halving) for x in d];e=[s+x+((x*x//s)//2) for x in v]
        for _ in range(halving):e=[x*x//s for x in e]
        den=sum(e);assert s<=den<=len(row)*s
        result.append([x*s//den for x in e]);traces.append(dict(maximum=m,difference=d,exponential=e,denominator=den))
    return result,traces

def negative_log_reference(q,fraction):
    s=1<<fraction
    if not 1<=q<=s:raise ValueError('positive fixed probability required')
    shift=0;u=q
    while u<s//2:u*=2;shift+=1
    v=s-u;power=v;out=shift*round(s*math.log(2))
    for j in range(1,config()['approximation']['log_degree']+1):
        out+=power*(s//j)//s
        if j<config()['approximation']['log_degree']:power=power*v//s
    return out

def training_reference(p,x,w,labels,mask,c):
    fx=Fixed(c);s=fx.scale;mod=fx.mod;n=len(x);f=len(x[0]);h=len(w[0][0]);classes=len(w[1][0]);fraction=c['fraction_bits']
    t0=fx.mul(x,w[0],'train_XW0');z0=fx.mul(p,t0,'train_PT0');hidden=[[max(0,fx.signed(v)) for v in row] for row in z0]
    t1=fx.mul(hidden,w[1],'train_HW1');z1=fx.mul(p,t1,'train_PT1');prob,exp=probability_reference([[fx.signed(v) for v in row] for row in z1],fraction)
    count=sum(mask);assert count>0 and count&(count-1)==0
    losses=[]
    for i,on in enumerate(mask):
        if not on:losses.append(0);continue
        q=prob[i][labels[i]]
        if c['training_reference'].get('loss_mode')=='range_reduced':
            losses.append(negative_log_reference(q,fraction));continue
        assert q>=round(c['approximation']['minimum_training_probability_real']*s)
        v=s-q;power=v;loss=0
        for j in range(1,c['approximation']['log_degree']+1):
            loss+=fx.checked(power*(s//j),'loss product')//s
            if j<c['approximation']['log_degree']:power=fx.checked(power*v,'loss power')//s
        losses.append(loss)
    loss=[sum(losses)//count]
    d=[[(prob[i][j]-(s if labels[i]==j else 0))//count%mod if mask[i] else 0 for j in range(classes)] for i in range(n)]
    dt1=fx.mul(transpose(p),d,'train_dT1');dw1=fx.mul(transpose(hidden),dt1,'train_dW1');dh=fx.mul(dt1,transpose(w[1]),'train_dH');dz0=[[v if fx.signed(z)>0 else 0 for v,z in zip(rr,zz)] for rr,zz in zip(dh,z0)];dt0=fx.mul(transpose(p),dz0,'train_dT0');dw0=fx.mul(transpose(x),dt0,'train_dW0')
    lr=round(c['model_reference']['learning_rate']*s);gradients=[dw0,dw1];nextw=[[[fx.checked(fx.signed(v)-fx.checked(fx.signed(g)*lr,'update product')//s,'updated weight')%mod for v,g in zip(row,grow)] for row,grow in zip(ww,gg)] for ww,gg in zip(w,gradients)]
    flatten=lambda a:[v for row in a for v in row]
    return dict(transform0=flatten(t0),activation_input=flatten(z0),hidden=flatten(hidden),transform1=flatten(t1),logits=flatten(z1),probabilities=flatten(prob),loss=loss,logit_gradient=flatten(d),gradient0=flatten(dw0),gradient1=flatten(dw1),next_weights=flatten(nextw[0])+flatten(nextw[1])),nextw,fx.audit
