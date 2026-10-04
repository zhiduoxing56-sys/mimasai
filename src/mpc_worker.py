"""Independent server process. Reads only its own bundle, input and durable ledger."""
import argparse
import json
import os
import resource
import socket
import sys
import time
from pathlib import Path
from .mpc import Channel, Engine, Materials, ProtocolError, VERSION, ROOT, private_write, require, settings, public_descriptor

def main():
    p=argparse.ArgumentParser();p.add_argument('role',type=int);p.add_argument('directory');p.add_argument('session');p.add_argument('bits',type=int);p.add_argument('fd',type=int);p.add_argument('attempt');args=p.parse_args()
    role=args.role; own=Path(args.directory)/('S'+str(role));material=None;channel=None;success=False
    outputs=[]; stages=[]; code=None; active=None; private_reads=[]
    def audit(event,event_args):
        if event=='open' and isinstance(event_args[0],(str,bytes)):
            path=Path(os.fsdecode(event_args[0])).resolve()
            require(not any(path.is_relative_to(ROOT/folder) for folder in ('verification/fixtures','results','参考资料')),'REFERENCE_DATA_VIEW_VIOLATION')
            runtime=Path(args.directory).resolve()
            if path.is_relative_to(runtime) and path.relative_to(runtime).parts[0] in ('S0','S1','V'):
                require(path.is_relative_to(own.resolve()),'PRIVATE_VIEW_VIOLATION')
                if event_args[1]=='r': private_reads.append(path.relative_to(runtime).as_posix())
    sys.addaudithook(audit)
    try:
        require(role in (0,1),'ROLE')
        material=Materials(own/'preprocessing.json',role,args.session,args.bits)
        job=json.loads((own/'input.json').read_text())
        require(job['version']==VERSION and job['session']==args.session and job['role']==role and job['bits']==args.bits,'INPUT_BINDING')
        channel=Channel(socket.socket(fileno=args.fd),role,args.session,settings()['mpc'])
        descriptor=public_descriptor(job,material.batch)
        peer=channel.exchange(-1,'hello',[8],descriptor)
        require(peer==descriptor,'PUBLIC_SCHEDULE_MISMATCH')
        engine=Engine(role,args.bits,material,channel)
        for idx,op in enumerate(job['operations']):
            engine.op=idx;engine.components=[];started=time.perf_counter();start=channel.metrics().copy();before=material.cursor.copy()
            x=outputs[-1] if op.get('use_previous',False) and outputs else op['x'];y=op.get('y',[])
            require(not op.get('use_previous',False) or bool(outputs),'MISSING_PREVIOUS_OUTPUT')
            if 'previous_slice' in op:
                offset,count=op['previous_slice'];require(op.get('use_previous',False) and offset>=0 and count>0 and offset+count<=len(x),'PREVIOUS_SLICE');x=x[offset:offset+count]
            require(all(type(v)==int and 0<=v<engine.mod for v in x+y),'INPUT_RESIDUE')
            kind=op['type'];active=(idx,kind,started,start,before)
            if kind in ('add','sub','mul'):
                require(len(x)==len(y)==op['count'],'INPUT_SHAPE')
            elif kind in ('truncate','public_mul','sign','relu','range','checked_relu','select','fss_relu'): require(len(x)==op['count'],'INPUT_SHAPE')
            if kind=='precision_up':
                shift=op['fraction']-op['source_fraction'];k=op['source_fraction']+settings()['range_policy']['operand_bound_exponents']['score']+1
                require(shift>=0 and k+shift<=engine.bits,'PRECISION_SCALE_BOUND');engine.check_range(x,k);out=engine.public_mul(x,1<<shift)
            elif kind=='publish':
                from .model import publish
                out=publish(engine,own,x,op)
            elif kind=='loss':
                from .operators import cross_entropy
                out=cross_entropy(engine,x,y,*op['dims'],op['fraction'],op['training_mask'])
            elif kind=='gcn_scores':
                from .operators import inference_scores
                from .model import load
                require(op['dims'][0]==len(op['model']['node_order']) and op['dims'][1:]==op['model']['dimensions'] and op['fraction']==op['model']['fraction_bits'],'INFERENCE_MODEL_BINDING')
                weights=load(role,own/('model-'+op['model']['model_id']+'.json'),op['model'])
                trace=inference_scores(engine,x,op['p'],weights,op['dims'],op['fraction']);out=[v for row in trace.values() for v in row]
            elif kind=='train_step':
                from .operators import train_step
                nodes,features,width,classes=op['dims'];weights=outputs[-1][-(features*width+width*classes):] if op.get('weights_previous',False) else y
                require(all(type(v)==int and 0<=v<engine.mod for v in op['p']+op['labels']+op.get('indices',[])+op.get('edge_weights',[])),'TRAIN_RESIDUE')
                neighbors=dict(indices=op['indices'],weights=op['edge_weights'],degree=op['degree']) if op.get('aggregation','dense')=='indexed' else None
                trace=train_step(engine,x,op['p'],weights,op['labels'],op['dims'],op['fraction'],op['training_mask'],neighbors);out=[v for row in trace.values() for v in row]
            elif kind=='convergence':
                from .operators import convergence_step
                out_run,stop=convergence_step(engine,x,y,op['p'],op['threshold'],op['window'],op['iteration'],op['maximum']);out=out_run+stop
                if op.get('open_stop',False):
                    require(len(stop)==1,'STOP_FLAG_SHAPE');before_stop=channel.metrics();peer=channel.exchange(idx,'convergence_stop',[1],stop);flag=(stop[0]+peer[0])%engine.mod;require(flag in (0,1),'STOP_FLAG_VALUE');engine.components.append(dict(name='public_stop',flag=flag,rounds=1,bytes_sent=channel.metrics()['bytes_sent']-before_stop['bytes_sent']))
            elif kind in ('compare','divide','probability','gather','bounded_matmul'):
                from .operators import compare,divide_unsigned,probability,gather,bounded_matrix,assert_batch,compare_boolean,public
                if kind=='compare':out=compare(engine,x,y)
                elif kind=='divide':
                    engine.check_range(x,op['nbits']+1);engine.check_range(y,op['dbits']+1);assert_batch(engine,compare_boolean(engine,y,public(engine,1,len(y))),'DIVISOR_NOT_POSITIVE');assert_batch(engine,compare_boolean(engine,x,public(engine,0,len(x))),'NUMERATOR_NEGATIVE');out=divide_unsigned(engine,x,y,op['nbits'],op['dbits'])
                elif kind=='probability':out=probability(engine,x,*op['dims'],op['fraction'])
                elif kind=='gather':out=gather(engine,y,x,*op['dims'])
                else:out=bounded_matrix(engine,x,y,op['dims'],op['fraction'],op['bounds'][0],op['bounds'][1])
            elif kind=='add': out=engine.add(x,y)
            elif kind=='sub': out=engine.sub(x,y)
            elif kind=='public_mul': out=engine.public_mul(x,op['scalar'])
            elif kind=='mul': out=engine.multiply(x,y)
            elif kind=='truncate': out=engine.truncate(x,op['fraction'])
            elif kind=='sign': out=engine.sign(x)
            elif kind=='select':
                require(len(y)==len(x),'SELECT_SHAPE');out=engine.select(x,y)
            elif kind=='relu': out=engine.relu(x)
            elif kind=='range': out=engine.check_range(x,op['k'])
            elif kind=='checked_relu':
                engine.measured('range',lambda:engine.check_range(x,op['k']));out=engine.relu(x)
            elif kind=='fss_relu':
                engine.measured('range',lambda:engine.check_range(x,op['k']));out=engine.measured('fss_eval_select',lambda:engine.fss_relu(x,op['k']))
            elif kind=='he_aggregate':
                from .he import aggregate
                if 'he_slot' in op:require(Path(op['he_slot']).name==op['he_slot'] and not op['he_slot'].startswith('.'),'HE_SLOT_PATH')
                raw,he_profile=engine.measured('homomorphic_aggregate_convert',lambda:aggregate(engine,own/op['he_slot'] if 'he_slot' in op else own,op,x))
                engine.components[-1]['he_profile']=he_profile
                z=engine.measured('aggregate_exact_truncate',lambda:engine.truncate(raw,op['fraction']))
                if op.get('activation','boolean')=='none':out=raw+z
                else:
                    engine.measured('range',lambda:engine.check_range(z,op['k']))
                    h=engine.measured('fss_eval_select',lambda:engine.fss_relu(z,op['k'])) if op.get('activation','boolean')=='fss' else engine.relu(z)
                    out=raw+z+h
            elif kind=='hidden':
                nodes,features,width=op['dims']
                pp=op['p'];require(len(pp)==nodes*nodes and len(op['node_order'])==nodes and len(set(op['node_order']))==nodes and op['scale']==1<<op['fraction'],'HIDDEN_INTERFACE')
                require(all(type(v)==int and 0<=v<engine.mod for v in pp),'PROPAGATION_RESIDUE')
                t=engine.measured('XW0',lambda:engine.matrix(x,y,[nodes,features,width],op['fraction']))
                z=engine.measured('P_T0',lambda:engine.matrix(pp,t,[nodes,nodes,width],op['fraction']))
                engine.measured('range',lambda:engine.check_range(z,op['k']));h=engine.measured('fss_eval_select',lambda:engine.fss_relu(z,op['k'])) if op.get('activation','boolean')=='fss' else engine.relu(z)
                out=t+z+h  # test shares only, separate verifier restores traces
            elif kind=='matmul': out=engine.matrix(x,y,op['dims'],op.get('fraction',0))
            else: raise ProtocolError('OPERATION_TYPE')
            outputs.append(out)
            after=channel.metrics()
            stages.append({'operation':idx,'type':kind,'bytes_sent':after['bytes_sent']-start['bytes_sent'],'rounds':after['exchange_rounds']-start['exchange_rounds'],'elapsed_seconds':time.perf_counter()-started,'components':engine.components,'consumed':{k:material.cursor[k]-before[k] for k in before}})
            active=None
        success=True
    except ProtocolError as e: code=e.code
    except (OSError,ValueError,KeyError,TypeError,IndexError): code='LOCAL_INVALID_OR_IO'
    finally:
        if active and channel and material:
            idx,kind,started,start,before=active;after=channel.metrics()
            stages.append(dict(operation=idx,type=kind,error=code,elapsed_seconds=time.perf_counter()-started,bytes_sent=after['bytes_sent']-start['bytes_sent'],rounds=after['exchange_rounds']-start['exchange_rounds'],consumed={k:material.cursor[k]-before[k] for k in before}))
        if material: material.finish(success)
        if channel: channel.sock.close()
    metric={'pid':os.getpid(),'role':role,'session':args.session,'success':success,'error':code,'communication':channel.metrics() if channel else None,'preprocessing':material.metrics() if material else None,'operations':stages,'message_trace':channel.trace if channel else [],'loaded_private_files':private_reads,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    private_write(own/('metrics-'+args.attempt+'.json'),metric)
    if success: private_write(own/('output-'+args.attempt+'.json'),dict(version=VERSION,session=args.session,role=role,shares=outputs))
    print(json.dumps({'role':role,'success':success,'error':code}))
    return 0 if success else 2
if __name__=='__main__': raise SystemExit(main())
