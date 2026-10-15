"""HE conversion by private-input secure decryption, not ciphertext sanitization.
The key holder never receives the peer's evaluated ciphertext or clear phase.
"""
import itertools,json,math,os,secrets,struct,time
from pathlib import Path
from .mpc import require
from .operators import CostCounter,flatten,sub_bits

def add_bits(e,a,b):
    width=len(a);n=len(a[0]);p=[[x^y for x,y in zip(aa,bb)] for aa,bb in zip(a,b)];original=[r[:] for r in p]
    gg=e.boolean_and(flatten(a),flatten(b));g=[gg[j*n:(j+1)*n] for j in range(width)];distance=1
    while distance<width:
        left=flatten(p[distance:]);prod=e.boolean_and(left+left,flatten(g[:-distance])+flatten(p[:-distance]));size=len(left)
        g=g[:distance]+[[v^w for v,w in zip(g[j],prod[(j-distance)*n:(j-distance+1)*n])] for j in range(distance,width)]
        p=p[:distance]+[prod[size+(j-distance)*n:size+(j-distance+1)*n] for j in range(distance,width)];distance*=2
    return [[v^w for v,w in zip(original[j],g[j-1] if j else [0]*n)] for j in range(width)]

def round_phase(e,local,q):
    """Exact BFV round(t*(a0+a1 mod q)/q) mod t as arithmetic shares.
    Local quotients are corrected using TWO SECRET carry comparisons.
    q is odd; no halfway tie with power-of-two t. No phase/remainder opened.
    """
    require(type(q)==int and q%2==1 and q>e.mod and q.bit_length()<=256 and len(local)>0,'BFV_ROUND_DOMAIN')
    require(all(type(v)==int and 0<=v<q for v in local),'BFV_PHASE_SHARE_DOMAIN')
    n=len(local);width=q.bit_length()+1;t=e.mod
    quotient=[v*t//q for v in local];remainder=[v*t%q for v in local]
    own=[[(v>>j)&1 for v in remainder] for j in range(width)];zeros=[[0]*n for _ in range(width)]
    total=add_bits(e,own if e.role==0 else zeros,own if e.role==1 else zeros)
    thresholds=[q-q//2,2*q-q//2];public=[[(thresholds[k]>>j)&1 if e.role==0 else 0 for k in range(2) for _ in range(n)] for j in range(width)]
    _,carry=sub_bits(e,[row+row for row in total],public);converted=e.b2a([carry[:n],carry[n:]])
    return [(v+a+b)%t for v,a,b in zip(quotient,*converted)]

def round_cost(n,q,bits=32):
    e=CostCounter(bits);round_phase(e,[0]*n,q);return e.counts

def read_poly(path,degree,qs):
    data=Path(path).read_bytes();require(len(data)==8*degree*len(qs),'RING_POLYNOMIAL_LENGTH');v=list(struct.unpack('<'+'Q'*(degree*len(qs)),data))
    require(all(0<=x<q for l,q in enumerate(qs) for x in v[l*degree:(l+1)*degree]),'RING_POLYNOMIAL_RESIDUE');return v

def crt(values,qs):
    q=math.prod(qs);factors=[(q//p)*pow(q//p,-1,p) for p in qs];return sum(v*f for v,f in zip(values,factors))%q

def secure_convert(engine,own,op,mask,ids):
    """Actual packed BFV ciphertext -> exact secret plaintext -> output shares."""
    from .he import native,binary_write
    own=Path(own);n,cols=op['he']['shape'];degree=op['he']['degree'];qs=op['he']['data_moduli'];q=math.prod(qs);size=degree*len(qs);start=time.perf_counter()
    exported=native(['export_ring_inputs',own,cols]);require(exported['data_moduli']==qs,'RING_CONTEXT_BINDING')
    # Public binding plus fresh mask IDs; NO evaluated ciphertext is transmitted.
    descriptor=dict(version='private-bfv-decryption-v1',he=op['he'],operation=engine.op,mask_ids=ids)
    payload=json.dumps(descriptor,sort_keys=True,separators=(',',':')).encode();peer=bytes(engine.channel.exchange(engine.op,'he_secure_binding',[len(payload)],payload,'byte'))
    other=json.loads(peer);peerids=other.pop('mask_ids',[]);expected=dict(descriptor);expected.pop('mask_ids');require(other==expected and len(peerids)==cols and len(set(peerids))==cols,'RING_PEER_BINDING');engine.materials.claim_he_ids(peerids,'peer')
    secret=read_poly(own/'peer-key-coefficients.bin',degree,qs);phase_shares=[];ring_seconds=0
    for key in range(2):
        items,span=engine.materials.take('rlwe_product',cols)
        group=items[0].get('reuse_group')
        require(isinstance(group,str) and len(group)==32 and all(item.get('reuse_group')==group and item.get('group_size')==cols for item in items),'RING_REUSE_GROUP_BINDING')
        triples=[];d_parts=[];b_first=None
        for col,item in enumerate(items):
            folder=Path(item['folder']);require(not folder.is_absolute() and '..' not in folder.parts,'RING_PREPROCESS_PATH')
            triple=Path(engine.materials.directory)/folder;require(triple.resolve().is_relative_to(Path(engine.materials.directory).resolve()),'RING_PREPROCESS_PATH');require(item['degree']==degree and item['data_moduli']==qs,'RING_PREPROCESS_CONTEXT')
            a=read_poly(triple/'a.bin',degree,qs);b=read_poly(triple/'b.bin',degree,qs)
            if b_first is None:b_first=b
            else:require(b==b_first,'RING_REUSE_MASK_MISMATCH')
            x=read_poly(own/f'cipher-{col}-1.bin',degree,qs) if engine.role==key else [0]*size
            d_parts.append([(v-w)%p for l,p in enumerate(qs) for v,w in zip(x[l*degree:(l+1)*degree],a[l*degree:(l+1)*degree])]);triples.append(triple)
        y=secret if engine.role!=key else [0]*size
        local_e=[(v-w)%p for l,p in enumerate(qs) for v,w in zip(y[l*degree:(l+1)*degree],b_first[l*degree:(l+1)*degree])]
        encoded=struct.pack('<'+'Q'*((cols+1)*size),*itertools.chain.from_iterable((*d_parts,local_e)))
        received=bytes(engine.channel.exchange(engine.op,'rlwe_beaver_masks_grouped',[len(encoded)],encoded,'byte',span+[group]+[item['material_id'] for item in items]))
        opened=list(struct.unpack('<'+'Q'*((cols+1)*size),received))
        require(all(v<p for part in range(cols+1) for l,p in enumerate(qs) for v in opened[part*size+l*degree:part*size+(l+1)*degree]),'RING_MESSAGE_RESIDUE')
        ee=[(v+w)%p for l,p in enumerate(qs) for v,w in zip(local_e[l*degree:(l+1)*degree],opened[cols*size+l*degree:cols*size+(l+1)*degree])]
        for col,(item,triple,d) in enumerate(zip(items,triples,d_parts)):
            dd=[(v+w)%p for l,p in enumerate(qs) for v,w in zip(d[l*degree:(l+1)*degree],opened[col*size+l*degree:col*size+(l+1)*degree])]
            run=own/'secure-products'/item['material_id'];(run/'ring-work').mkdir(parents=True,mode=0o700);os.link(own/'parameters.seal',run/'parameters.seal');binary_write(run/'ring-work/d.bin',struct.pack('<'+'Q'*size,*dd));binary_write(run/'ring-work/e.bin',struct.pack('<'+'Q'*size,*ee))
            local=native(['ring_evaluate',run,engine.role,triple,run/'product.bin','no_decryption']);ring_seconds+=local['elapsed_seconds'];product=read_poly(run/'product.bin',degree,qs)
            c0=read_poly(own/f'cipher-{col}-0.bin',degree,qs) if engine.role==key else [0]*size
            for row in range(n):phase_shares.append(crt([(product[l*degree+row]+c0[l*degree+row])%p for l,p in enumerate(qs)],qs))
    rounded=engine.measured('private_BFV_round',lambda:round_phase(engine,phase_shares,q))
    # key-major / column-major input, node-major model output. Masks belong only
    # to the originating evaluator, so add its mask once after exact rounding.
    result=[(rounded[col*n+row]+rounded[cols*n+col*n+row]+mask[col*degree+row])%engine.mod for row in range(n) for col in range(cols)]
    return result,dict(conversion_seconds=time.perf_counter()-start,ring_local_seconds=ring_seconds,conversion='private_input_secure_decryption',evaluated_ciphertexts_sent=0,clear_decryptions=0,phase_elements=2*n*cols,ring_triples=2*cols,modulus_bits=q.bit_length())
