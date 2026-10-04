"""Fixed-shape secret circuits over the existing trusted-offline MPC engine.
All arithmetic outputs are additive shares; no reconstruction in this module.
"""
import math
from .mpc import require,range_cost,settings

def public(e,v,n):return [v%e.mod if e.role==0 else 0]*n
def invert(e,a):return [v^int(e.role==0) for v in a]
def flatten(rows):return [v for row in rows for v in row]
def transpose(a,rows,cols):return [a[i*cols+j] for j in range(cols) for i in range(rows)]
def sub_bits(e,a,b):
    """Parallel-prefix a + ~b + 1; returns difference and unsigned >= bit."""
    width=len(a);n=len(a[0]);nb=[invert(e,row) for row in b];p=[[x^y for x,y in zip(aa,bb)] for aa,bb in zip(a,nb)];original=[row[:] for row in p]
    gg=e.boolean_and(flatten(a),flatten(nb));g=[gg[j*n:(j+1)*n] for j in range(width)]
    distance=1
    while distance<width:
        left=flatten(p[distance:]);right_g=flatten(g[:-distance]);right_p=flatten(p[:-distance]);prod=e.boolean_and(left+left,right_g+right_p);size=len(left)
        nextg=g[:distance]+[[v^w for v,w in zip(g[j],prod[(j-distance)*n:(j-distance+1)*n])] for j in range(distance,width)]
        nextp=p[:distance]+[prod[size+(j-distance)*n:size+(j-distance+1)*n] for j in range(distance,width)]
        g,p=nextg,nextp;distance*=2
    carries=[[int(e.role==0)]*n]+[[v^w for v,w in zip(g[j-1],p[j-1])] for j in range(1,width)]
    out=[[v^w for v,w in zip(row,carry)] for row,carry in zip(original,carries)];ge=[v^w for v,w in zip(g[-1],p[-1])]
    return out,ge

def compare_boolean(e,a,b):
    """Arithmetic unit bit of signed a>=b, exact full ring (no a-b overflow)."""
    wires=e.a2b(a+b);n=len(a);aa=[row[:n] for row in wires];bb=[row[n:] for row in wires]
    aa[-1]=invert(e,aa[-1]);bb[-1]=invert(e,bb[-1]);_,ge=sub_bits(e,aa,bb);return ge
def compare(e,a,b):return e.b2a([compare_boolean(e,a,b)])[0]
def choose(e,bit,yes,no):return e.add(no,e.multiply(bit,e.sub(yes,no)))
def maximum(e,a,b):return choose(e,compare(e,a,b),a,b)

def assert_batch(e,valid,code):
    while len(valid)>1:
        end=len(valid)//2*2;reduced=e.boolean_and(valid[:end:2],valid[1:end:2]);valid=reduced+valid[-1:] if len(valid)%2 else reduced
    if not isinstance(e,CostCounter):
        peer=e.channel.exchange(e.op,'operator_batch_valid',[1],valid,'bit');require(valid[0]^peer[0]==1,code)

def divide_unsigned(e,numerator,denominator,nbits,dbits):
    """Exact floor for positive denominator; caller establishes public bounds.
    Restoring binary division with prefix subtraction and Boolean selection.
    """
    require(0<nbits<e.bits and 0<dbits<e.bits,'DIVISION_WIDTH');n=len(numerator);require(len(denominator)==n,'DIVISION_SHAPE')
    wires=e.a2b(numerator+denominator);num=[row[:n] for row in wires[:nbits]];den=[row[n:] for row in wires[:dbits]]+[[0]*n];width=dbits+1
    remainder=[[0]*n for _ in range(width)];quotient=[]
    for bit in reversed(num):
        remainder=[bit]+remainder[:-1];difference,ge=sub_bits(e,remainder,den)
        diff=flatten([[a^b for a,b in zip(x,y)] for x,y in zip(remainder,difference)])
        selected=e.boolean_and(diff,ge*width);remainder=[[a^b for a,b in zip(remainder[j],selected[j*n:(j+1)*n])] for j in range(width)]
        quotient.append(ge)
    ar=e.b2a(list(reversed(quotient)));return [sum(ar[j][i]*(1<<j) for j in range(nbits))%e.mod for i in range(n)]

def probability(e,scores,rows,classes,fraction,guard=True):
    """Independent bounded approximation, NOT SEAF/Bolt/IRON softmax kernel.
    clip d at -8S; v=floor(d/16); T2(v)^16; exact positive division.
    """
    approx=settings()['approximation'];halving=approx['exp_halving_bits']
    require(classes>=2 and rows>0 and fraction>=halving and 2*fraction+1<e.bits,'PROBABILITY_DOMAIN');s=1<<fraction
    require(0<approx['exp_clip_real']<=1<<(halving-1) and classes*s<1<<(e.bits-1),'PROBABILITY_PUBLIC_BOUND')
    require(len(scores)==rows*classes,'PROBABILITY_SHAPE')
    if guard:e.check_range(scores,fraction+5) # [-16,16) in real units
    maxima=[scores[i*classes] for i in range(rows)]
    for j in range(1,classes):maxima=maximum(e,maxima,[scores[i*classes+j] for i in range(rows)])
    diff=e.sub(scores,[v for v in maxima for _ in range(classes)])
    diff=maximum(e,diff,public(e,-approx['exp_clip_real']*s,len(diff)));v=e.truncate(diff,halving)
    square=e.truncate(e.multiply(v,v),fraction);half=e.truncate(square,1)
    exp=e.add(e.add(public(e,s,len(v)),v),half)
    for _ in range(halving):exp=e.truncate(e.multiply(exp,exp),fraction)
    sums=[sum(exp[i*classes:(i+1)*classes])%e.mod for i in range(rows)]
    # max-difference is exactly zero in each row => exp(max)=S => sums>=S.
    # All exp in [0,S], so denominator<=classes*S; no denominator is opened.
    numerator=e.public_mul(exp,s);den=[v for v in sums for _ in range(classes)]
    result=divide_unsigned(e,numerator,den,2*fraction+1,fraction+classes.bit_length())
    return result

def bounded_matrix(e,a,b,dims,fraction,kx,ky):
    rows,inner,cols=dims
    require(inner*(1<<(kx-1))*(1<<(ky-1))<(1<<(e.bits-1)),'PUBLIC_DOT_BOUND_UNSAFE')
    e.check_range(a,kx);e.check_range(b,ky)
    return e.matrix(a,b,dims,fraction)

def gather(e,array,indices,rows,cols):
    """Full linear scan; no online helper; index range batch flag only."""
    require(len(array)==rows*cols and rows>0 and cols>0 and len(indices)>0,'GATHER_SHAPE');n=len(indices);w=e.a2b(indices)
    # Equality for every public candidate, balanced secret AND reduction.
    match=[]
    for j in range(rows):
        bits=[row[:] if (j>>b)&1 else invert(e,row) for b,row in enumerate(w)]
        while len(bits)>1:
            count=len(bits)//2;prod=e.boolean_and(flatten(bits[:2*count:2]),flatten(bits[1:2*count:2]));out=[prod[q*n:(q+1)*n] for q in range(count)];bits=out+bits[-1:] if len(bits)%2 else out
        match.append(bits[0])
    # The equality flags are mutually exclusive; XOR is OR here.
    valid=[0]*n
    for row in match:valid=[a^b for a,b in zip(valid,row)]
    allvalid=valid
    while len(allvalid)>1:
        end=len(allvalid)//2*2;out=e.boolean_and(allvalid[:end:2],allvalid[1:end:2]);allvalid=out+allvalid[-1:] if len(allvalid)%2 else out
    if not isinstance(e,CostCounter):
        other=e.channel.exchange(e.op,'index_batch_valid',[1],allvalid,'bit');require(allvalid[0]^other[0]==1,'INDEX_RANGE_REJECTED')
    arithmetic=e.b2a(match);left=[];right=[]
    for q in range(n):
        for c in range(cols):
            for j in range(rows):left.append(arithmetic[j][q]);right.append(array[j*cols+c])
    products=e.multiply(left,right);return [sum(products[i:i+rows])%e.mod for i in range(0,len(products),rows)]

class CostCounter:
    """OFFLINE public resource planning only; never a server/test protocol backend."""
    def __init__(self,bits):self.bits=bits;self.mod=1<<bits;self.role=0;self.counts=dict(arithmetic=0,boolean=0,dabit=0,fss=0)
    def add(self,a,b):return [0]*len(a)
    sub=add
    def public_mul(self,a,b):return [0]*len(a)
    def multiply(self,a,b):self.counts['arithmetic']+=len(a);return [0]*len(a)
    def boolean_and(self,a,b):self.counts['boolean']+=len(a);return [0]*len(a)
    def a2b(self,a):self.counts['boolean']+=2*(self.bits-1)*len(a);return [[0]*len(a) for _ in range(self.bits)]
    def b2a(self,a):self.counts['dabit']+=len(a)*len(a[0]);return [[0]*len(a[0]) for _ in a]
    def truncate(self,a,f):self.counts['boolean']+=2*(self.bits-1)*len(a);self.counts['dabit']+=(self.bits-f)*len(a);return [0]*len(a)
    def check_range(self,a,k):self.counts['boolean']+=range_cost(len(a),self.bits,k);return []
    def measured(self,name,fn):return fn()
    def matrix(self,a,b,dims,f):
        from .mpc import Engine
        return Engine.matrix(self,a,b,dims,f)
    def sign(self,a):return self.b2a([self.a2b(a)[-1]])[0]
    def relu(self,a):return choose(self,self.sub(public(self,1,len(a)),self.sign(a)),a,[0]*len(a))

def cross_entropy(e,prob,labels,n,classes,fraction,mask):
    s=1<<fraction;count=sum(mask);require(count>0 and count&(count-1)==0,'TRAIN_POWER_TWO_MASK_COUNT');shift=count.bit_length()-1
    require(len(prob)==len(labels)==n*classes and classes*s<1<<(e.bits-1),'LOSS_SHAPE')
    # Prove [0,S] probabilities and well-formed secret one-hot label words.
    valid=compare_boolean(e,prob+public(e,s,len(prob)),public(e,0,len(prob))+prob)
    assert_batch(e,valid,'PROBABILITY_VALUE_DOMAIN')
    wires=e.a2b(labels);label_bits=[invert(e,row) for j,row in enumerate(wires) if j!=fraction]
    units=e.b2a([wires[fraction]])[0];sums=[sum(units[i*classes:(i+1)*classes])%e.mod for i in range(n)]
    equal=compare_boolean(e,sums+public(e,1,n),public(e,1,n)+sums)
    assert_batch(e,flatten(label_bits)+equal,'LABEL_ONE_HOT_DOMAIN')
    selected=e.truncate(e.multiply(prob,labels),fraction);truep=[sum(selected[i*classes:(i+1)*classes])%e.mod for i in range(n)]
    guarded=[truep[i] if mask[i] else (s if e.role==0 else 0) for i in range(n)]
    low=round(settings()['approximation']['minimum_training_probability_real']*s)
    assert_batch(e,compare_boolean(e,guarded,public(e,low,n)),'LOSS_PROBABILITY_DOMAIN')
    v=e.sub(public(e,s,n),guarded);power=v[:];loss_terms=[0]*n
    for j in range(1,settings()['approximation']['log_degree']+1):
        term=e.truncate(e.public_mul(power,s//j),fraction);loss_terms=e.add(loss_terms,term)
        if j<settings()['approximation']['log_degree']:power=e.truncate(e.multiply(power,v),fraction)
    loss=[sum(loss_terms[i] for i,on in enumerate(mask) if on)%e.mod];loss=e.truncate(loss,shift) if shift else loss
    return loss

def train_step(e,x,p,w,labels,dims,fraction,mask,neighbors=None):
    n,features,hidden,classes=dims;s=1<<fraction;policy=settings()['range_policy']['operand_bound_exponents'];bounds=lambda name:fraction+policy[name]+1
    require(len(x)==n*features and (len(p)==n*n or neighbors is not None) and len(w)==features*hidden+hidden*classes and len(labels)==n*classes,'TRAIN_SHAPE');require(len(mask)==n and all(type(v)==bool for v in mask),'TRAIN_MASK')
    count=sum(mask);require(count>0 and count&(count-1)==0,'TRAIN_POWER_TWO_MASK_COUNT');shift=count.bit_length()-1
    a=w[:features*hidden];b=w[features*hidden:]
    mat=lambda aa,bb,dd,ka,kb:bounded_matrix(e,aa,bb,dd,fraction,bounds(ka),bounds(kb))
    aggregate=lambda states,width: indexed_aggregate(e,states,neighbors['indices'],neighbors['weights'],n,width,neighbors['degree'],fraction) if neighbors is not None else mat(p,states,[n,n,width],'propagation','state')
    t0=e.measured('train_XW0',lambda:mat(x,a,[n,features,hidden],'feature','weight'))
    z0=e.measured('train_PT0',lambda:aggregate(t0,hidden))
    e.check_range(z0,bounds('state'));h=e.measured('train_relu',lambda:e.relu(z0))
    t1=e.measured('train_HW1',lambda:mat(h,b,[n,hidden,classes],'state','weight'))
    z1=e.measured('train_PT1',lambda:aggregate(t1,classes))
    prob=e.measured('train_probability',lambda:probability(e,z1,n,classes,fraction))
    loss=e.measured('train_loss',lambda:cross_entropy(e,prob,labels,n,classes,fraction,mask))
    d=e.sub(prob,labels);d=[v if mask[i//classes] else 0 for i,v in enumerate(d)];d=e.truncate(d,shift) if shift else d
    pt=transpose(p,n,n) if neighbors is None else None;dt1=e.measured('train_dT1',lambda:aggregate(d,classes) if neighbors is not None else mat(pt,d,[n,n,classes],'propagation','error'))
    dw1=e.measured('train_dW1',lambda:mat(transpose(h,n,hidden),dt1,[hidden,n,classes],'state','backprop_state'))
    dh=e.measured('train_dH',lambda:mat(dt1,transpose(b,hidden,classes),[n,classes,hidden],'backprop_state','weight'))
    e.check_range(dh,bounds('state'));positive=compare(e,z0,public(e,1,len(z0)));dz0=e.multiply(dh,positive)
    dt0=e.measured('train_dT0',lambda:aggregate(dz0,hidden) if neighbors is not None else mat(pt,dz0,[n,n,hidden],'propagation','state'))
    dw0=e.measured('train_dW0',lambda:mat(transpose(x,n,features),dt0,[features,n,hidden],'feature','state'))
    gradients=dw0+dw1;e.check_range(gradients,bounds('gradient'))
    rate=round(settings()['model_reference']['learning_rate']*s)
    require((1<<(bounds('gradient')-1))*abs(rate)<1<<(e.bits-1),'LEARNING_RATE_PRODUCT_BOUND')
    update=e.truncate(e.public_mul(gradients,rate),fraction);nextw=e.sub(w,update);e.check_range(nextw,bounds('weight'))
    return dict(transform0=t0,activation_input=z0,hidden=h,transform1=t1,logits=z1,probabilities=prob,loss=loss,logit_gradient=d,gradient0=dw0,gradient1=dw1,next_weights=nextw)

def convergence_step(e,previous,current,run,threshold,window,iteration,maximum):
    # Inputs are bounded nonnegative losses, current ring delta cannot overflow.
    require(window>0 and maximum>0 and 0<iteration<=maximum and threshold>=0,'CONVERGENCE_PUBLIC_DOMAIN')
    e.check_range(previous+current,settings()['training_reference']['fraction_bits']+4);e.check_range(run,window.bit_length()+2)
    delta=e.sub(current,previous);positive=compare(e,delta,public(e,0,len(delta)));absolute=choose(e,positive,delta,e.public_mul(delta,-1));within=compare(e,public(e,threshold,len(delta)),absolute)
    next_run=e.multiply(within,e.add(run,public(e,1,len(run))));stop=compare(e,next_run,public(e,window,len(run)))
    if iteration>=maximum:stop=public(e,1,len(run))
    return next_run,stop

def plan_operator(op,bits):
    e=CostCounter(bits);kind=op['type'];n=op.get('count',0)
    if kind=='train_step':
        nodes,features,h,c=op['dims'];neighbors=dict(indices=[0]*(nodes*op['degree']),weights=[0]*(nodes*op['degree']),degree=op['degree']) if op.get('aggregation','dense')=='indexed' else None;train_step(e,[0]*(nodes*features),[0]*(nodes*nodes),[0]*(features*h+h*c),[0]*(nodes*c),op['dims'],op['fraction'],op['training_mask'],neighbors)
    elif kind=='loss':cross_entropy(e,[0]*n,[0]*n,*op['dims'],op['fraction'],op['training_mask'])
    elif kind=='convergence':convergence_step(e,[0]*n,[0]*n,[0]*n,op['threshold'],op['window'],op['iteration'],op['maximum'])
    return e.counts

def inference_scores(e,x,p,w,dims,fraction):
    n,features,h,c=dims;policy=settings()['range_policy']['operand_bound_exponents'];bounds=lambda name:fraction+policy[name]+1
    a=w[:features*h];b=w[features*h:];mat=lambda aa,bb,dd,ka,kb:bounded_matrix(e,aa,bb,dd,fraction,bounds(ka),bounds(kb))
    t0=e.measured('inference_XW0',lambda:mat(x,a,[n,features,h],'feature','weight'))
    z0=e.measured('inference_PT0',lambda:mat(p,t0,[n,n,h],'propagation','state'));e.check_range(z0,bounds('state'));hidden=e.relu(z0)
    t1=e.measured('inference_HW1',lambda:mat(hidden,b,[n,h,c],'state','weight'))
    logits=e.measured('inference_PT1',lambda:mat(p,t1,[n,n,c],'propagation','state'))
    return dict(transform0=t0,activation_input=z0,hidden=hidden,transform1=t1,logits=logits)

def indexed_aggregate(e,states,indices,weights,n,width,degree,fraction):
    """Secret neighbor lookup + weighted dot, once-only rescale of each dot."""
    b=settings()['range_policy']['operand_bound_exponents'];kx=fraction+b['state']+1;kw=fraction+b['propagation']+1
    require(len(indices)==len(weights)==n*degree and len(states)==n*width,'INDEXED_GRAPH_SHAPE')
    require(degree*(1<<(kx-1))*(1<<(kw-1))<(1<<(e.bits-1)),'PUBLIC_GRAPH_BOUND_UNSAFE')
    e.check_range(states,kx);e.check_range(weights,kw)
    selected=gather(e,states,indices,n,width);expanded=[value for value in weights for _ in range(width)]
    products=e.multiply(expanded,selected);raw=[sum(products[(i*degree+j)*width+c] for j in range(degree))%e.mod for i in range(n) for c in range(width)]
    return e.truncate(raw,fraction)
