"""Two-party passive MPC with a trusted, input-independent offline dealer.
No input/intermediate reconstruction API is provided in this module.
"""
import json
import hashlib
import math
import os
import resource
import socket
import sqlite3
import struct
import time
from pathlib import Path

VERSION = 'privacy-gnn-mpc-v1'
ROOT = Path(__file__).resolve().parents[1]

class ProtocolError(Exception):
    def __init__(self,code):
        self.code=code
        super().__init__(code)

def require(ok,code):
    if not ok: raise ProtocolError(code)

def settings():
    return json.loads((ROOT/'config/phase0.json').read_text())

def private_write(path,data):
    path=Path(path)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        json.dump(data,f,separators=(',',':')); f.write('\n'); f.flush(); os.fsync(f.fileno())

class Materials:
    """Claim the whole batch before online execution; abort burns unused entries.
    A fixed per-role durable ledger rejects replay even from a copied bundle.
    """
    def __init__(self,path,role,session,bits):
        self.data=json.loads(Path(path).read_text())
        require(self.data['version']==VERSION and self.data['role']==role and self.data['session']==session and self.data['bits']==bits,'PREPROCESSING_BINDING')
        self.directory=Path(path).parent
        self.role=role; self.session=session; self.batch=self.data['batch']
        ledger=ROOT/'state/mpc'/('S'+str(role)+'-ledger.sqlite')
        ledger.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(ledger,timeout=5)
        os.chmod(ledger,0o600)
        # Retain rollback journaling: system SQLite 3.45.1 lacks the WAL-reset fix.
        # Mode conversion checkpoints committed state; never remove sidecars.
        require(self.db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete','LEDGER_DURABILITY_MODE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (batch TEXT PRIMARY KEY, session TEXT, state TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS consumption (batch TEXT, kind TEXT, idx INTEGER, PRIMARY KEY(batch,kind,idx))')
        self.db.execute('CREATE TABLE IF NOT EXISTS consumption_spans (batch TEXT, kind TEXT, start INTEGER, count INTEGER, PRIMARY KEY(batch,kind,start))')
        try:
            with self.db: self.db.execute('INSERT INTO batches VALUES (?,?,?)',(self.batch,session,'reserved_burn_on_abort'))
        except sqlite3.IntegrityError: raise ProtocolError('BATCH_ALREADY_RESERVED') from None
        self.db.execute('CREATE TABLE IF NOT EXISTS he_masks (direction TEXT, mask_id TEXT, session TEXT, batch TEXT, PRIMARY KEY(direction,mask_id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS ring_materials (material_id TEXT PRIMARY KEY, session TEXT, batch TEXT)')
        ring_ids=[item['material_id'] for item in self.data['materials'].get('rlwe_product',[])]
        require(len(set(ring_ids))==len(ring_ids) and all(isinstance(v,str) and len(v)==32 for v in ring_ids),'RING_MATERIAL_IDS')
        try:
            with self.db:
                for value in ring_ids:self.db.execute('INSERT INTO ring_materials VALUES (?,?,?)',(value,session,self.batch))
        except sqlite3.IntegrityError:raise ProtocolError('RING_MATERIAL_REUSE') from None
        self.cursor={k:0 for k in self.data['materials']}
    def take(self,kind,count):
        require(type(count)==int and count>=0,'MATERIAL_COUNT')
        start=self.cursor.get(kind,0)
        values=self.data['materials'].get(kind,[])
        require(start+count<=len(values),'PREPROCESSING_EXHAUSTED')
        with self.db:
            if count:
                self.db.execute('INSERT INTO consumption_spans VALUES (?,?,?,?)',(self.batch,kind,start,count))
            if kind=='he_mask':self.claim_he_ids(values[start:start+count],'local')
        self.cursor[kind]=start+count
        return values[start:start+count],[kind,start,count]
    def claim_he_ids(self,ids,direction):
        require(all(isinstance(v,str) and len(v)==32 for v in ids),'HE_MASK_IDENTIFIERS')
        try:
            with self.db:
                for value in ids:self.db.execute('INSERT INTO he_masks VALUES (?,?,?,?)',(direction,value,self.session,self.batch))
        except sqlite3.IntegrityError:raise ProtocolError('HE_MASK_IDENTIFIER_REUSE') from None
    def finish(self,success):
        with self.db: self.db.execute('UPDATE batches SET state=? WHERE batch=?',('completed' if success else 'aborted_burned',self.batch))
    def metrics(self):
        return {'batch':self.batch,'consumed':self.cursor,'reserved':{k:len(v) for k,v in self.data['materials'].items()},'unused_policy':'burned; batch never resumed'}

class Channel:
    def __init__(self,sock,role,session,c):
        self.sock=sock; self.role=role; self.session=session; self.seq=0
        self.sock.settimeout(c['timeout_seconds']); self.limit=c['max_frame_bytes']
        self.sent=self.received=0; self.trace=[]
    def read_exact(self,n):
        data=bytearray()
        while len(data)<n:
            piece=self.sock.recv(n-len(data))
            require(bool(piece),'DISCONNECTED')
            data.extend(piece)
            self.received+=len(piece)
        return bytes(data)
    def frame(self,op,kind,shape,values,dtype,span):
        require(math.prod(shape)==len(values),'LOCAL_SHAPE')
        if dtype=='byte':
            require(all(type(v)==int and 0<=v<256 for v in values),'LOCAL_BYTE')
            payload=bytes(values)
        elif dtype=='bit':
            require(all(type(v)==int and v in (0,1) for v in values),'LOCAL_BIT')
            payload=bytes(values)
        else:
            require(all(type(v)==int and 0<=v<1<<32 for v in values),'LOCAL_RING')
            payload=struct.pack('<'+'I'*len(values),*values)
        header={'version':VERSION,'session':self.session,'sequence':self.seq,'operation':op,'type':kind,'shape':shape,'dtype':dtype,'payload_length':len(payload),'material_span':span}
        encoded=json.dumps(header,sort_keys=True,separators=(',',':')).encode()
        body=struct.pack('!I',len(encoded))+encoded+payload
        require(len(body)<=self.limit,'LOCAL_FRAME_LIMIT')
        return struct.pack('!I',len(body))+body,header
    def send(self,frame):
        view=memoryview(frame)
        while view:
            n=self.sock.send(view)
            require(n>0,'DISCONNECTED')
            self.sent+=n; view=view[n:]
    def receive(self,expected):
        size=struct.unpack('!I',self.read_exact(4))[0]
        require(4<=size<=self.limit,'FRAME_LENGTH')
        body=self.read_exact(size); hsize=struct.unpack('!I',body[:4])[0]
        require(0<hsize<=size-4,'HEADER_LENGTH')
        try: header=json.loads(body[4:4+hsize])
        except (ValueError,UnicodeError): raise ProtocolError('HEADER_JSON') from None
        require(json.dumps(header,sort_keys=True,separators=(',',':'))==json.dumps(expected,sort_keys=True,separators=(',',':')),'MESSAGE_METADATA')
        payload=body[4+hsize:]
        require(len(payload)==expected['payload_length'],'PAYLOAD_LENGTH')
        if expected['dtype']=='byte': return list(payload)
        if expected['dtype']=='bit':
            require(all(v<2 for v in payload),'PAYLOAD_BIT')
            return list(payload)
        require(len(payload)%4==0,'PAYLOAD_ALIGNMENT')
        return list(struct.unpack('<'+'I'*(len(payload)//4),payload))
    def exchange(self,op,kind,shape,values,dtype='u32',span=None):
        frame,expected=self.frame(op,kind,shape,values,dtype,span)
        try:
            if self.role==0:
                self.send(frame); peer=self.receive(expected)
            else:
                peer=self.receive(expected); self.send(frame)
        except socket.timeout: raise ProtocolError('TIMEOUT') from None
        except OSError: raise ProtocolError('TRANSPORT_FAILURE') from None
        self.trace.append({k:expected[k] for k in ('sequence','operation','type','shape','dtype','payload_length','material_span')})
        self.seq+=1
        return peer
    def metrics(self): return {'bytes_sent':self.sent,'bytes_received':self.received,'exchange_rounds':self.seq}

def public_descriptor(job,batch):
    plan=[{k:v for k,v in op.items() if k not in ('x','y','p','labels','indices','edge_weights','q_share')} for op in job['operations']]
    encoded=json.dumps(dict(version=VERSION,bits=job['bits'],batch=batch,plan=plan),sort_keys=True,separators=(',',':')).encode()
    # Hash of public schedule only, never of secret values/parameters.
    return list(struct.unpack('<8I',hashlib.sha256(encoded).digest()))

class Engine:
    def __init__(self,role,bits,materials,channel):
        self.role=role; self.bits=bits; self.mod=1<<bits; self.materials=materials; self.channel=channel; self.op=0; self.components=[]
    def add(self,x,y):
        require(len(x)==len(y),'ADD_SHAPE')
        return [(a+b)%self.mod for a,b in zip(x,y)]
    def sub(self,x,y):
        require(len(x)==len(y),'SUBTRACT_SHAPE')
        return [(a-b)%self.mod for a,b in zip(x,y)]
    def public_mul(self,x,k):
        require(type(k)==int,'PUBLIC_SCALAR')
        return [(a*k)%self.mod for a in x]
    def multiply(self,x,y):
        require(len(x)==len(y),'MULTIPLY_SHAPE')
        triples,span=self.materials.take('arithmetic',len(x))
        d=[(v-t[0])%self.mod for v,t in zip(x,triples)]
        e=[(v-t[1])%self.mod for v,t in zip(y,triples)]
        peer=self.channel.exchange(self.op,'arithmetic_masks',[2,len(x)],d+e,span=span)
        dd=self.add(d,peer[:len(x)]); ee=self.add(e,peer[len(x):])
        return [(t[2]+a*t[1]+b*t[0]+(a*b if self.role==0 else 0))%self.mod for t,a,b in zip(triples,dd,ee)]
    def boolean_and(self,x,y):
        triples,span=self.materials.take('boolean',len(x))
        d=[v^t[0] for v,t in zip(x,triples)]; e=[v^t[1] for v,t in zip(y,triples)]
        peer=self.channel.exchange(self.op,'boolean_masks',[2,len(x)],d+e,'bit',span)
        dd=[a^b for a,b in zip(d,peer[:len(x)])]; ee=[a^b for a,b in zip(e,peer[len(x):])]
        return [t[2]^(a&t[1])^(b&t[0])^((a&b) if self.role==0 else 0) for t,a,b in zip(triples,dd,ee)]
    def a2b(self,x):
        """Bits of the modular sum, not the individual arithmetic-share bits."""
        n=len(x); carry=[0]*n; wires=[]
        for bit in range(self.bits):
            own=[(v>>bit)&1 for v in x]
            aa=own if self.role==0 else [0]*n
            bb=own if self.role==1 else [0]*n
            prop=[a^b for a,b in zip(aa,bb)]
            wires.append([v^c for v,c in zip(prop,carry)])
            if bit<self.bits-1:
                products=self.boolean_and(aa+prop,bb+carry)
                carry=[a^b for a,b in zip(products[:n],products[n:])]
        return wires
    def b2a(self,wires):
        n=len(wires[0]); flat=[v for row in wires for v in row]
        dabits,span=self.materials.take('dabit',len(flat))
        masked=[v^r[0] for v,r in zip(flat,dabits)]
        peer=self.channel.exchange(self.op,'dabit_masks',[len(wires),n],masked,'bit',span)
        opened=[a^b for a,b in zip(masked,peer)]
        arithmetic=[(r[1] if c==0 else (int(self.role==0)-r[1])%self.mod) for c,r in zip(opened,dabits)]
        return [arithmetic[j*n:(j+1)*n] for j in range(len(wires))]
    def truncate(self,x,fraction):
        require(0<fraction<self.bits,'TRUNCATION_SHIFT')
        n=len(x); kept=self.a2b(x)[fraction:]; converted=self.b2a(kept)
        output=[0]*n
        for j in range(len(kept)):
            weight=(1<<j) if j<len(kept)-1 else -(1<<j)
            for i in range(n): output[i]=(output[i]+weight*converted[j][i])%self.mod
        return output
    def measured(self,name,fn):
        started=time.perf_counter();before=self.channel.metrics();used=self.materials.cursor.copy()
        value=fn();after=self.channel.metrics()
        self.components.append(dict(name=name,process_highwater_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children_highwater_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,elapsed_seconds=time.perf_counter()-started,bytes_sent=after['bytes_sent']-before['bytes_sent'],rounds=after['exchange_rounds']-before['exchange_rounds'],consumed={k:self.materials.cursor[k]-used[k] for k in used}))
        return value
    def sign(self,x):
        # Arithmetic bit 1 iff negative. No fractional scale.
        return self.b2a([self.a2b(x)[-1]])[0]
    def select(self,x,bit):
        return self.multiply(x,bit)  # scale S * unit bit = S, no truncation
    def relu(self,x):
        negative=self.measured('sign',lambda:self.sign(x))
        nonnegative=[(int(self.role==0)-v)%self.mod for v in negative]
        return self.measured('select',lambda:self.select(x,nonnegative))
    def check_range(self,x,k):
        require(type(k)==int and 1<=k<=self.bits and len(x)>0,'RANGE_ARGUMENT')
        if k==self.bits:
            valid=int(self.role==0)
        else:
            wires=self.a2b(x)
            # Equality of all upper bits to bit k-1, reduced across the batch.
            equal=[int(self.role==0)^hi^lo for row in wires[k:] for hi,lo in zip(row,wires[k-1])]
            while len(equal)>1:
                left=equal[0:len(equal)-1:2];right=equal[1:len(equal):2]
                reduced=self.boolean_and(left,right)
                equal=reduced+equal[-1:] if len(equal)%2 else reduced
            valid=equal[0]
        peer=self.channel.exchange(self.op,'range_batch_flag',[1],[valid],'bit')
        flag=valid^peer[0]  # explicitly authorized one-bit batch leakage
        require(flag==1,'RANGE_REJECTED')
        return []
    def fss_relu(self,x,k):
        # Caller must finish the secret batch-range guard first.
        from .fss import comparison_eval
        materials,span=self.materials.take('fss',len(x))
        require(all(v['key']['bits']==k-1 for v in materials),'FSS_WIDTH_BINDING')
        masks=[(v+r['rz_share'])%self.mod for v,r in zip(x,materials)]
        peer=self.channel.exchange(self.op,'fss_input_mask',[len(x)],masks,span=span)
        public=self.add(masks,peer);half=1<<(k-1)
        shares=[]
        for value,r in zip(public,materials):
            pk=value%(1<<k);q=half-1-(pk%half)
            comparison=comparison_eval(self.role,r['key'],q)
            # Stage-zero correction: public MSB only to S0, correct rp_i.
            shares.append(comparison^r['rp_share']^((pk//half) if self.role==0 else 0))
        other=self.channel.exchange(self.op,'fss_masked_choice',[len(x)],shares,'bit',span)
        masked=[a^b for a,b in zip(shares,other)]
        return [(r['mux'][h][0]*v+r['mux'][h][1])%self.mod for v,r,h in zip(public,materials,masked)]
    def matrix(self,x,y,dims,fraction):
        require(len(dims)==3 and all(type(d)==int and d>0 for d in dims),'MATRIX_DIMENSIONS')
        rows,inner,cols=dims
        require(len(x)==rows*inner and len(y)==inner*cols,'MATRIX_SHAPE')
        left=[];right=[]
        for i in range(rows):
            for j in range(cols):
                for k in range(inner): left.append(x[i*inner+k]);right.append(y[k*cols+j])
        products=self.multiply(left,right)
        raw=[sum(products[s:s+inner])%self.mod for s in range(0,len(products),inner)]
        return self.truncate(raw,fraction) if fraction else raw

def range_cost(n,bits,k):
    require(1<=k<=bits,'RANGE_ARGUMENT')
    return 0 if k==bits else 2*(bits-1)*n+max(n*(bits-k)-1,0)

def costs(plan,bits):
    counts=dict(arithmetic=0,boolean=0,dabit=0,fss=0)
    if any(op['type']=='he_aggregate' for op in plan): counts['he_mask']=0
    if any(op['type']=='publish' for op in plan):counts['refresh']=0
    for op in plan:
        kind=op['type'];n=op.get('count',0)
        if kind=='matmul' and 'model' in op:
            from .operators import CostCounter,bounded_matrix
            e=CostCounter(bits);e.range_strategy=op.get('range_strategy','dimension');r,k,c=op['dims'];bounded_matrix(e,[0]*(r*k),[0]*(k*c),op['dims'],op['fraction'],*op['bounds'])
            for key in e.counts:counts[key]+=e.counts[key]
            continue
        if kind=='shared_aggregate':
            r,k,c=op['dims'];sub=[dict(type='bounded_matmul',count=r*c,dims=op['dims'],fraction=op['fraction'],bounds=op['bounds'],range_strategy=op.get('range_strategy','dimension'))]
            if op.get('activation','none')!='none':sub.append(dict(type='fss_relu' if op['activation']=='fss' else 'checked_relu',count=r*c,k=op['k']))
            cc=costs(sub,bits)
            for key in cc:counts[key]+=cc[key]
            continue
        if kind=='negative_log':
            from .operators import CostCounter,negative_log
            e=CostCounter(bits);negative_log(e,[0]*n,op['fraction'])
            for key in e.counts:counts[key]+=e.counts[key]
            continue
        if kind=='bfv_round':
            from .he_secure import round_cost
            cc=round_cost(n,int(op['ciphertext_modulus']),bits)
            for key in cc:counts[key]+=cc[key]
            continue
        if kind=='precision_up':
            shift=op['fraction']-op['source_fraction'];k=op['source_fraction']+settings()['range_policy']['operand_bound_exponents']['score']+1
            require(shift>=0 and k+shift<=bits,'PRECISION_SCALE_BOUND')
            counts['boolean']+=range_cost(n,bits,k);continue
        if kind=='publish':
            counts['refresh']+=n;counts['boolean']+=range_cost(n,bits,op['source_fraction']+3)+range_cost(n,bits,op['model']['fraction_bits']+3)
            drop=op['source_fraction']-op['model']['fraction_bits']
            require(drop>=0,'UNVERIFIED_PRECISION_INCREASE')
            if drop:counts['boolean']+=2*(bits-1)*n;counts['dabit']+=(bits-drop)*n
            continue
        if kind=='gcn_scores':
            from .operators import CostCounter,inference_scores
            e=CostCounter(bits);e.range_strategy=op.get('range_strategy','dimension');nn,ff,hh,cc=op['dims'];inference_scores(e,[0]*(nn*ff),[0]*(nn*nn),[0]*(ff*hh+hh*cc),op['dims'],op['fraction'])
            for key in counts:counts[key]+=e.counts.get(key,0)
            continue
        if kind in ('train_step','convergence','loss'):
            from .operators import plan_operator
            cc=plan_operator(op,bits)
            for key in counts:counts[key]+=cc.get(key,0)
            continue
        if kind in ('compare','divide','probability','gather','bounded_matmul'):
            from .operators import CostCounter,compare,divide_unsigned,probability,gather,bounded_matrix,assert_batch,compare_boolean,public
            e=CostCounter(bits);e.range_strategy=op.get('range_strategy','dimension');x=[0]*n
            if kind=='compare':compare(e,x,x)
            elif kind=='divide':
                e.check_range(x,op['nbits']+1);e.check_range(x,op['dbits']+1);assert_batch(e,compare_boolean(e,x,public(e,1,n)),'DIVISOR_NOT_POSITIVE');assert_batch(e,compare_boolean(e,x,public(e,0,n)),'NUMERATOR_NEGATIVE');divide_unsigned(e,x,x,op['nbits'],op['dbits'])
            elif kind=='probability':probability(e,x,*op['dims'],op['fraction'])
            elif kind=='gather':gather(e,[0]*(op['dims'][0]*op['dims'][1]),x,*op['dims'])
            else:bounded_matrix(e,[0]*(op['dims'][0]*op['dims'][1]),[0]*(op['dims'][1]*op['dims'][2]),op['dims'],op['fraction'],op['bounds'][0],op['bounds'][1])
            for key in counts:counts[key]+=e.counts.get(key,0)
            continue
        if kind=='mul': counts['arithmetic']+=n
        elif kind in ('sign','relu','checked_relu'):
            counts['boolean']+=2*(bits-1)*n;counts['dabit']+=n
            if kind!='sign':counts['arithmetic']+=n
            if kind=='checked_relu':counts['boolean']+=range_cost(n,bits,op['k'])
        elif kind=='fss_relu':
            counts['boolean']+=range_cost(n,bits,op['k']);counts['fss']+=n
        elif kind=='range': counts['boolean']+=range_cost(n,bits,op['k'])
        elif kind=='he_aggregate':
            require(op.get('conversion') in ('legacy_ciphertext','private_decryption'),'HE_CONVERSION_TYPE')
            counts['he_mask']+=op['he']['shape'][1]
            if 'input_bound' in op:counts['boolean']+=range_cost(n,bits,op['input_bound'])
            if op.get('conversion')=='private_decryption':
                from .he_secure import round_cost
                counts['rlwe_product']=counts.get('rlwe_product',0)+2*op['he']['shape'][1]
                cc=round_cost(2*n,math.prod(op['he']['data_moduli']),bits)
                for key in cc:counts[key]+=cc[key]
            sub=[dict(type='truncate',count=n,fraction=op['fraction'])]
            if op.get('activation','boolean')!='none':sub.append(dict(type=('fss_relu' if op.get('activation','boolean')=='fss' else 'checked_relu'),count=n,k=op['k']))
            cc=costs(sub,bits)
            for name in cc:counts[name]+=cc[name]
        elif kind=='hidden':
            nodes,features,width=op['dims']
            sub=[dict(type='matmul',dims=[nodes,features,width],fraction=op['fraction']),dict(type='matmul',dims=[nodes,nodes,width],fraction=op['fraction']),dict(type=('fss_relu' if op.get('activation','boolean')=='fss' else 'checked_relu'),count=nodes*width,k=op['k'])]
            cc=costs(sub,bits)
            for name in counts:counts[name]+=cc[name]
        if kind=='select':counts['arithmetic']+=n
        if kind=='matmul':
            a,b,c=op['dims'];counts['arithmetic']+=a*b*c;n=a*c if op.get('fraction',0) else 0
        elif kind!='truncate':n=0
        if n:
            counts['boolean']+=2*(bits-1)*n;counts['dabit']+=(bits-op['fraction'])*n
    return counts

def fss_widths(plan):
    widths=[]
    for op in plan:
        if op['type'] in ('he_aggregate','shared_aggregate') and op.get('activation','boolean')=='fss':widths.extend([op['k']]*op['count'])
        elif op['type']=='fss_relu': widths.extend([op['k']]*op['count'])
        elif op['type']=='hidden' and op.get('activation','boolean')=='fss':widths.extend([op['k']]*(op['dims'][0]*op['dims'][2]))
    return widths
