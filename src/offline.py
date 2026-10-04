"""Trusted offline dealer: accepts only public dimensions and random session ID."""
import argparse
import json
import secrets
import time
from pathlib import Path
from .mpc import VERSION, private_write, costs, require, fss_widths

def generate(directory,session,bits,plan,limits=None):
    require(2<=bits<=32,'DEALER_BITS')
    for op in plan:
        require(set(op)<=set(['type','count','dims','fraction','scalar','k','node_order','scale','activation','he','use_previous','previous_slice','he_slot','nbits','dbits','bounds','training_mask','weights_previous','threshold','window','iteration','maximum','open_stop','model','source_fraction','aggregation','degree']),'DEALER_NONPUBLIC_FIELDS')
    counts=costs(plan,bits)
    if limits: counts.update(limits)
    mod=1<<bits; batch=secrets.token_hex(16)
    views=[{k:[] for k in counts} for _ in range(2)]
    widths=iter(fss_widths(plan));fss_seconds=0.0
    for kind,count in counts.items():
        for _ in range(count):
            if kind=='arithmetic':
                a=secrets.randbelow(mod);b=secrets.randbelow(mod); values=[a,b,a*b%mod]
                share=[secrets.randbelow(mod) for v in values]
                views[0][kind].append(share);views[1][kind].append([(v-r)%mod for v,r in zip(values,share)])
            elif kind=='boolean':
                a=secrets.randbits(1);b=secrets.randbits(1); values=[a,b,a&b]
                share=[secrets.randbits(1) for v in values]
                views[0][kind].append(share);views[1][kind].append([v^r for v,r in zip(values,share)])
            elif kind=='refresh':
                for role in (0,1):views[role][kind].append(secrets.randbits(bits))
            elif kind=='he_mask':
                for role in (0,1):views[role][kind].append(secrets.token_hex(16))
            elif kind=='fss':
                from .fss import activation_material
                started=time.perf_counter();pair=activation_material(bits,next(widths));fss_seconds+=time.perf_counter()-started
                for role in (0,1):views[role][kind].append(pair[role])
            else:
                r=secrets.randbits(1); rb=secrets.randbits(1);ra=secrets.randbelow(mod)
                views[0][kind].append([rb,ra]); views[1][kind].append([r^rb,(r-ra)%mod])
    for role in range(2):
        private_write(Path(directory)/('S'+str(role))/'preprocessing.json',dict(version=VERSION,session=session,batch=batch,role=role,bits=bits,materials=views[role]))
    return {'session':session,'batch':batch,'bits':bits,'generated':counts,'online_inputs_accessed':False,'fss_keygen_seconds':fss_seconds}

def main():
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('plan');args=p.parse_args()
    doc=json.loads(Path(args.plan).read_text())
    result=generate(args.directory,doc['session'],doc['bits'],doc['plan'],doc.get('limits'))
    print(json.dumps(result,separators=(',',':')))
if __name__=='__main__': main()
