"""Real comparison FSS over F2 from fixed-count prefix DPFs.
BGI optimized DPF (2018/707, Fig.1), independently implemented in Python.
PRG: domain-separated SHAKE256 with 128-bit seeds, computational assumption.
No threshold, truth table, or paired root seeds are included in a server key.
"""
import hashlib
import secrets
from .mpc import require

def xor(a,b): return bytes(u^v for u,v in zip(a,b))
def expand(seed):
    raw=hashlib.shake_256(b'privacy-gnn-dpf-expand-v1\0'+seed).digest(33)
    return [raw[:16],raw[16:32]],[raw[32]&1,(raw[32]>>1)&1]
def convert(seed): return hashlib.shake_256(b'privacy-gnn-dpf-convert-v1\0'+seed).digest(1)[0]&1

def dpf_generate(alpha,beta,bits):
    require(0<=alpha<1<<bits and beta in (0,1),'DPF_ARGUMENT')
    roots=[secrets.token_bytes(16),secrets.token_bytes(16)];ss=roots[:];tt=[0,1];words=[]
    for level in range(bits):
        children=[expand(s) for s in ss]
        keep=(alpha>>(bits-1-level))&1;lose=keep^1
        sc=xor(children[0][0][lose],children[1][0][lose])
        tc=[children[0][1][0]^children[1][1][0]^keep^1,children[0][1][1]^children[1][1][1]^keep]
        words.append([sc.hex(),tc[0],tc[1]])
        old=tt[:]
        ss=[xor(children[b][0][keep],sc) if old[b] else children[b][0][keep] for b in (0,1)]
        tt=[children[b][1][keep]^(old[b]&tc[keep]) for b in (0,1)]
    final=beta^convert(ss[0])^convert(ss[1])
    return [dict(root=roots[b].hex(),words=words,final=final) for b in (0,1)]

def dpf_eval(role,key,x,bits):
    require(len(key['words'])==bits and 0<=x<1<<bits,'DPF_KEY_SHAPE')
    seed=bytes.fromhex(key['root']);require(len(seed)==16,'DPF_SEED_LENGTH');control=role
    for level,(sc,tl,tr) in enumerate(key['words']):
        child,t=expand(seed);branch=(x>>(bits-1-level))&1
        # Eval path depends only on masked public x, not a secret threshold.
        correction=bytes.fromhex(sc);require(len(correction)==16 and tl in (0,1) and tr in (0,1),'DPF_CORRECTION')
        seed=xor(child[branch],bytes(v*control for v in correction))
        control=t[branch]^(control&[tl,tr][branch])
    return convert(seed)^(control&key['final'])

def comparison_generate(alpha,bits):
    require(0<=alpha<1<<bits,'DCF_ARGUMENT')
    keys=[dict(format='prefix-dpf-comparison-f2-v1',bits=bits,role=b,prefixes=[]) for b in (0,1)]
    # A zero-payload DPF is still generated at EVERY level: no alpha-bit leakage.
    for width in range(1,bits+1):
        prefix=(alpha>>(bits-width))&~1;payload=(alpha>>(bits-width))&1
        pair=dpf_generate(prefix,payload,width)
        for b in (0,1):keys[b]['prefixes'].append(pair[b])
    return keys

def comparison_eval(role,key,x):
    bits=key['bits']
    require(key['format']=='prefix-dpf-comparison-f2-v1' and key['role']==role and len(key['prefixes'])==bits and 0<=x<1<<bits,'DCF_KEY_BINDING')
    result=0
    for width,part in enumerate(key['prefixes'],1):result^=dpf_eval(role,part,x>>(bits-width),width)
    return result

def activation_material(bits,k):
    require(1<=k<=bits,'FSS_RANGE_ARGUMENT')
    mod=1<<bits;half=1<<(k-1);rz=secrets.randbelow(mod);rb=secrets.randbits(1)
    negative=(-rz)%(1<<k);rp=(negative//half)^1^rb
    keys=comparison_generate(negative%half,k-1)
    rz0=secrets.randbelow(mod);rp0=secrets.randbits(1)
    views=[dict(key=keys[b],rz_share=(rz0 if b==0 else (rz-rz0)%mod),rp_share=(rp0 if b==0 else rp^rp0),mux=[]) for b in (0,1)]
    for masked in (0,1):
        bit=masked^rb;a0=secrets.randbelow(mod);b0=secrets.randbelow(mod)
        views[0]['mux'].append([a0,b0]);views[1]['mux'].append([(bit-a0)%mod,(-bit*rz-b0)%mod])
    return views
