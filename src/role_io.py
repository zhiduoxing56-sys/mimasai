"""Role-bound private I/O. No reconstruction; coordinator receives metadata only."""
import argparse,copy,json,os,sys
from pathlib import Path
from .mpc import ROOT,VERSION,require,private_write
from .query import validate_delivery

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=('publication_input','query_input','export'));p.add_argument('role',type=int,choices=(0,1));p.add_argument('source');p.add_argument('destination');p.add_argument('--attempt');a=p.parse_args();source=Path(a.source).resolve();destination=Path(a.destination).resolve();own=f'S{a.role}'
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(ROOT/'build'):
                parts=path.relative_to(ROOT/'build').parts
                require(not any(v in ('S0','S1','V') and v!=own for v in parts),'ROLE_IO_PRIVATE_VIEW')
            if any(path.is_relative_to(ROOT/folder) for folder in ('results','state','data','verification/fixtures','参考资料')):
                # Only write this role's final export, never read results.
                flags=args[2] if len(args)>2 else 0
                final_write=path==destination/f'{own}.json' and flags & os.O_WRONLY
                directory_sync=path==destination and flags & os.O_DIRECTORY
                require(a.operation=='export' and (final_write or directory_sync),'ROLE_IO_RESULT_VIEW')
    sys.addaudithook(audit)
    require(source.is_relative_to(ROOT/'build') and (a.operation=='export' or destination.is_relative_to(ROOT/'build')),'ROLE_IO_PATH')
    read=lambda path:json.loads(path.read_text())
    if a.operation=='publication_input':
        plan=read(destination/'public-plan.json');checkpoint=read(source/own/f'output-{a.attempt}.json');require(checkpoint['role']==a.role and checkpoint['version']==VERSION and checkpoint['session']==source.name,'ROLE_IO_CHECKPOINT');jobs=copy.deepcopy(plan['plan']);count=jobs[0]['count'];jobs[0]['x']=checkpoint['shares'][0][-count:];jobs[1]['x']=[];private_write(destination/own/'input.json',dict(version=VERSION,session=plan['session'],role=a.role,bits=plan['bits'],operations=jobs))
    elif a.operation=='query_input':
        template=read(destination/'job-template.json');jobs=copy.deepcopy(template['operations'])
        for op in jobs:op['x']=[]
        if jobs[0]['type']!='load_hidden':
            inputs=read(source/own/'input-shares.json');jobs[0]['x']=inputs['x']
            if template['route']=='shared':
                for i in (1,3):jobs[i]['p']=inputs['p']
        private_write(destination/own/'input.json',dict(version=VERSION,session=template['session'],role=a.role,bits=template['bits'],operations=jobs,delivery=template['delivery']))
    else:
        job=read(source/own/'input.json');validate_delivery(job,read(source/own/'query-policy.json'));result=read(source/own/f'output-{a.attempt}.json');policy=job['delivery'];model=policy['model'];require(result['role']==a.role and result['session']==job['session'] and result['delivery']==policy,'ROLE_IO_RESULT_BINDING');require(len(result['shares'])==1 and len(result['shares'][0])==len(policy['targets'])*len(model['class_order']),'ROLE_IO_FINAL_ONLY');private_write(destination/f'{own}.json',dict(version='authorized-probability-shares-v1',role=a.role,request_id=job['session'],receiver_id=policy['receiver_id'],model_id=model['model_id'],targets=policy['targets'],classes=model['class_order'],fraction=model['probability_fraction_bits'],ring_bits=model['ring_bits'],shares=result['shares'][0]))
    print(json.dumps(dict(status='ROLE_IO_COMPLETE',role=a.role,operation=a.operation)))
if __name__=='__main__':main()
