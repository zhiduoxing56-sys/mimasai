"""Plaintext numerical and persistence references. No secure protocol backend."""
import copy
import hashlib
import json
import math
import secrets
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def config():
    c=json.loads((ROOT / "config/phase0.json").read_text())
    fixture=json.loads((ROOT / "verification/fixtures/gcn-reference.json").read_text())
    for name,fields in [("graph_reference",fixture["graph"]),("model_reference",fixture["model"])]:
        if set(c[name]) & set(fields): raise ValueError("duplicate fixture/config fields")
        c[name].update(fields)
    return c
def transpose(a):
    return [list(x) for x in zip(*a)]
def mm(a,b):
    if not a or not b or any(len(row)!=len(b) for row in a):
        raise ValueError("matrix shape")
    return [[sum(x*y for x,y in zip(row,col)) for col in transpose(b)] for row in a]
def graph(g):
    if g['duplicate_policy']!='sum_weights' or g['self_loop_policy']!='reject_input_then_add_unit_once':
        raise ValueError('unsupported graph policy')
    n=g['nodes']
    if len(g['node_order'])!=n or len(set(g['node_order']))!=n or len(g['features'])!=n:
        raise ValueError("node order/features")
    if not g['features'] or not g['features'][0] or any(len(row)!=len(g['features'][0]) or any(not math.isfinite(x) for x in row) for row in g['features']):
        raise ValueError("features")
    a=[[0.0]*n for _ in range(n)]
    for edge in g['undirected_edges']:
        if len(edge)!=3: raise ValueError("weighted undirected edge requires three fields")
        u,v,w=edge
        if type(u)!=int or type(v)!=int or not 0<=u<n or not 0<=v<n or u==v or not math.isfinite(w) or w<0:
            raise ValueError("invalid edge / input self-loop")
        a[u][v]+=w
        a[v][u]+=w
    for i in range(n): a[i][i]=1.0
    d=list(map(sum,a))
    if any(not math.isfinite(v) for v in d): raise ValueError("nonfinite degree")
    return a,d,[[a[i][j]/math.sqrt(d[i]*d[j]) for j in range(n)] for i in range(n)]
def softmax(z):
    out=[]
    for row in z:
        ex=[math.exp(x-max(row)) for x in row]
        out.append([x/sum(ex) for x in ex])
    return out
def precise_softmax(z):
    with localcontext() as ctx:
        ctx.prec=80
        out=[]
        for row in z:
            ds=[Decimal(str(x)) for x in row]
            es=[(x-max(ds)).exp() for x in ds]
            out.append([str(x/sum(es)) for x in es])
        return out
def forward(p,x,w):
    t0=mm(x,w[0]); z0=mm(p,t0)
    h=[[max(0,v) for v in row] for row in z0]
    t1=mm(h,w[1]); z1=mm(p,t1)
    return dict(propagation=p,transform0=t0,activation_input=z0,hidden=h,transform1=t1,logits=z1,probabilities=softmax(z1))
def loss_grad(p,x,w,labels,mask):
    if len(mask)!=len(x) or any(type(v)!=bool for v in mask) or not any(mask) or len(labels)!=len(x):
        raise ValueError("training mask must be nonempty boolean [N]")
    f=forward(p,x,w); count=sum(mask); loss=0.0
    dz=[]
    for i,row in enumerate(f['logits']):
        if type(labels[i])!=int or not 0<=labels[i]<len(row): raise ValueError("label")
        if mask[i]: loss+=(max(row)+math.log(sum(math.exp(v-max(row)) for v in row))-row[labels[i]])/count
        dz.append([(v-int(j==labels[i]))/count if mask[i] else 0.0 for j,v in enumerate(f['probabilities'][i])])
    dr1=mm(transpose(p),dz)
    g1=mm(transpose(f['hidden']),dr1)
    dh=mm(dr1,transpose(w[1]))
    da=[[v*int(z>0) for v,z in zip(row,zrow)] for row,zrow in zip(dh,f['activation_input'])]
    dr0=mm(transpose(p),da); g0=mm(transpose(x),dr0)
    f['gradients']=[g0,g1]; f['loss']=loss
    f['logit_gradient']=dz
    return loss,[g0,g1],f
def convergence(changes,threshold,window,max_iterations):
    if threshold<0 or window<1 or max_iterations<1: raise ValueError("convergence settings")
    consecutive=0
    for i,diff in enumerate(changes[:max_iterations],1):
        if not math.isfinite(diff) or diff<0: raise ValueError("invalid change")
        consecutive=consecutive+1 if diff<=threshold else 0
        if consecutive>=window: return {'stop':True,'iteration':i,'reason':'threshold_window'}
    return {'stop':len(changes)>=max_iterations,'iteration':min(len(changes),max_iterations),'reason':'max_iterations' if len(changes)>=max_iterations else 'continue'}

class Fixed:
    def __init__(self,c):
        self.bits=c['ring_bits']; self.scale=1<<c['fraction_bits']; self.mod=1<<self.bits; self.bound=self.mod//2; self.audit=[]
    def checked(self,v,where):
        if not -self.bound<=v<self.bound: raise OverflowError(f"{where}: {v} outside signed ring")
        return v
    def signed(self,v):
        if type(v)!=int or not 0<=v<self.mod: raise ValueError("ring residue")
        return v if v<self.bound else v-self.mod
    def encode(self,a):
        return [[self.checked(round(v*self.scale),'encode')%self.mod for v in row] for row in a]
    def decode(self,a): return [[self.signed(v)/self.scale for v in row] for row in a]
    def mul(self,a,b,name):
        out=[]; raw=[]; maxproduct=0; maxpartial=0
        for row in a:
            rr=[]; oo=[]
            if len(row)!=len(b): raise ValueError("matrix shape")
            for col in transpose(b):
                acc=0; ring_acc=0
                for u,v in zip(row,col):
                    product=self.checked(self.signed(u)*self.signed(v),name+' product')
                    acc=self.checked(acc+product,name+' partial accumulation')
                    ring_acc=(ring_acc+u*v)%self.mod
                    assert self.signed(ring_acc)==acc
                    maxproduct=max(maxproduct,abs(product)); maxpartial=max(maxpartial,abs(acc))
                rr.append(acc); oo.append(self.checked(acc//self.scale,name+' floor rescale')%self.mod)
            raw.append(rr); out.append(oo)
        self.audit.append(dict(operation=name,product_scale=self.scale**2,accumulator_scale=self.scale**2,output_scale=self.scale,max_abs_product=maxproduct,max_abs_partial_sum=maxpartial,raw_accumulators=raw))
        return out
    def forward(self,p,x,w,order):
        if order=='transform_then_aggregate':
            t0=self.mul(x,w[0],'XW0'); z0=self.mul(p,t0,'P(XW0)')
        elif order=='aggregate_then_transform':
            t0=self.mul(p,x,'PX'); z0=self.mul(t0,w[0],'(PX)W0')
        else: raise ValueError('order')
        h=[[max(0,self.signed(v))%self.mod for v in row] for row in z0]
        if order=='transform_then_aggregate':
            t1=self.mul(h,w[1],'HW1'); z1=self.mul(p,t1,'P(HW1)')
        else:
            t1=self.mul(p,h,'PH'); z1=self.mul(t1,w[1],'(PH)W1')
        return dict(transform0=t0,activation_input=z0,hidden=h,transform1=t1,logits=z1,probabilities=precise_softmax(self.decode(z1)),audit=copy.deepcopy(self.audit))
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def binding(c):
    m=c['model_reference']; g=c['graph_reference']
    if m['bias']!='public_fixed_zero' or m['activations']!=['relu','softmax_without_relu'] or m['query']!='full_graph_then_select' or m['inference_order']!='transform_then_aggregate':
        raise ValueError('unsupported model semantics')
    p=graph(g)[2]
    return dict(propagation_identifier=digest(p),model_version=m['version'],node_order=g['node_order'],graph_preprocessing={'undirected':True,'nonnegative':True,'duplicates':g['duplicate_policy'],'self_loops':g['self_loop_policy']},graph_identifier=digest(g),layer_dimensions=[len(g['features'][0]),m['hidden_width'],m['classes']],bias=m['bias'],activations=m['activations'],query=m['query'],ring_bits=c['ring_bits'],fraction_bits=c['fraction_bits'],rounding=c['rounding'],truncation_order=m['inference_order'],truncation='signed_floor_after_each_matrix_product')
def validate_weights(w,c,residues=False):
    dims=binding(c)['layer_dimensions']; mod=1<<c['ring_bits']
    if len(w)!=2: raise ValueError('layer count')
    for l in range(2):
        if len(w[l])!=dims[l] or any(len(row)!=dims[l+1] for row in w[l]): raise ValueError('weight shape')
        for row in w[l]:
            for v in row:
                if residues:
                    if type(v)!=int or not 0<=v<mod: raise ValueError('share residue')
                elif not math.isfinite(v): raise ValueError('nonfinite weight')
def save_model(path,w,c):
    validate_weights(w,c)
    Path(path).write_text(json.dumps(dict(format='plaintext-reference-only-v1',binding=binding(c),parameter_identifier=digest(w),weights=w),indent=2)+'\n')
def load_model(path,c):
    d=json.loads(Path(path).read_text())
    if d['format']!='plaintext-reference-only-v1' or d['binding']!=binding(c) or d['parameter_identifier']!=digest(d['weights']): raise ValueError('model binding/hash mismatch')
    validate_weights(d['weights'],c); return d['weights']
def split_test(w,c):
    validate_weights(w,c,True); mod=1<<c['ring_bits']; generation=secrets.token_hex(16)
    a=[[[secrets.randbelow(mod) for v in row] for row in layer] for layer in w]
    b=[[[ (v-r)%mod for v,r in zip(row,rr)] for row,rr in zip(layer,rl)] for layer,rl in zip(w,a)]
    return [dict(format='additive-reference-test-v1',role=role,binding=binding(c),parameter_identifier=digest(w),generation=generation,shares=v) for role,v in zip(['S0','S1'],[a,b])]
def recover_test(pair,c):
    a,b=pair
    if [a['role'],b['role']]!=['S0','S1'] or any(d['format']!='additive-reference-test-v1' or d['binding']!=binding(c) for d in pair) or a['generation']!=b['generation'] or a['parameter_identifier']!=b['parameter_identifier']: raise ValueError('share pair binding')
    for d in pair: validate_weights(d['shares'],c,True)
    mod=1<<c['ring_bits']
    w=[[[ (u+v)%mod for u,v in zip(row,col)] for row,col in zip(l,k)] for l,k in zip(a['shares'],b['shares'])]
    if digest(w)!=a['parameter_identifier']: raise ValueError('recovered reference hash')
    return w

def refresh_test(pair,c):
    # Test dealer sees both files. This is algebra, not a distributed refresh protocol.
    recover_test(pair,c)
    out=copy.deepcopy(pair); mod=1<<c['ring_bits']; generation=secrets.token_hex(16)
    for l,layer in enumerate(out[0]['shares']):
        for i,row in enumerate(layer):
            for j,v in enumerate(row):
                delta=secrets.randbelow(mod)
                out[0]['shares'][l][i][j]=(v+delta)%mod
                out[1]['shares'][l][i][j]=(out[1]['shares'][l][i][j]-delta)%mod
    for d in out: d['generation']=generation
    return out

def select_targets(probabilities,targets,node_order):
    if not targets or any(t not in node_order for t in targets) or len(set(targets))!=len(targets): raise ValueError('target identifiers')
    return [probabilities[node_order.index(t)] for t in targets]

def corrected_activation(z,n,k,rz,rb,t0,rp0):
    """Phase-zero suggested correction to HyGNN Alg.1; truth-table DCF only.
    Public MSB belongs only to S0; rp0/rp1 are XOR shares of offline rp.
    Caller is an independent test oracle that knows z, never an online protocol.
    """
    if not 1<k<n or not -(1<<(k-1))<=z<(1<<(k-1)): raise ValueError('outside certified shrink range')
    full,narrow,half=1<<n,1<<k,1<<(k-1)
    if not 0<=rz<full or any(v not in (0,1) for v in (rb,t0,rp0)): raise ValueError('mask')
    public=(z+rz)%full; pk=public%narrow; neg=(-rz)%narrow
    indicator=int(half-pk%half-1<neg%half)
    rp=neg//half ^ 1 ^ rb; rp1=rp0^rp; t1=t0^indicator
    s0=pk//half ^ t0 ^ rp0; s1=t1^rp1
    masked=s0^s1; b=masked^rb
    # Offline affine constants, one entry per possible public masked bit.
    keys=[]
    for h in (0,1):
        bit=h^rb
        keys.append(((1,2),((bit-1)%full,(-bit*rz-2)%full)))
    left,right=keys[masked]
    value=(left[0]*public+left[1]+right[0]*public+right[1])%full
    return dict(masked_sign_shares=[s0,s1],nonnegative=b,relu=value)
