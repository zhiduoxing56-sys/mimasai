"""Independent authorized recipient. Reads only two final target-share exports."""
import argparse,json,os,sys,time
from pathlib import Path
from .mpc import ROOT,require,private_write

FIELDS={'version','role','request_id','receiver_id','model_id','targets','classes','fraction','ring_bits','shares'}

def receive(directory,receiver_id):
    started=time.perf_counter();directory=Path(directory).resolve()
    require(directory.is_relative_to(ROOT/'results/application') and directory.parent.name=='receiver','RECEIVER_DIRECTORY')
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0])).resolve()
            if any(path.is_relative_to(ROOT/folder) for folder in ('build','state','data','results')):
                require(path.is_relative_to(directory),'RECEIVER_VIEW_VIOLATION')
    sys.addaudithook(audit)
    docs=[json.loads((directory/f'S{r}.json').read_text()) for r in (0,1)]
    for role,doc in enumerate(docs):
        require(set(doc)==FIELDS and doc['version']=='authorized-probability-shares-v1' and doc['role']==role,'RECEIVER_FORMAT')
        require(doc['receiver_id']==receiver_id and doc['request_id']==directory.name and len(doc['request_id'])==32 and all(v in '0123456789abcdef' for v in doc['request_id']) and len(doc['model_id'])==32 and all(v in '0123456789abcdef' for v in doc['model_id']),'RECEIVER_BINDING')
        require(doc['ring_bits']==32 and type(doc['fraction'])==int and 0<doc['fraction']<32,'RECEIVER_NUMERICS')
        require(isinstance(doc['targets'],list) and doc['targets'] and len(set(doc['targets']))==len(doc['targets']) and isinstance(doc['classes'],list) and len(doc['classes'])>=2 and len(set(doc['classes']))==len(doc['classes']),'RECEIVER_LAYOUT')
        require(len(doc['shares'])==len(doc['targets'])*len(doc['classes']) and all(type(v)==int and 0<=v<1<<32 for v in doc['shares']),'RECEIVER_SHAPE')
    require({k:v for k,v in docs[0].items() if k not in ('role','shares')}=={k:v for k,v in docs[1].items() if k not in ('role','shares')},'RECEIVER_PEER_BINDING')
    values=[(a+b)%(1<<32) for a,b in zip(docs[0]['shares'],docs[1]['shares'])];scale=1<<docs[0]['fraction'];require(all(0<=v<=scale for v in values),'RECEIVER_PROBABILITY_DOMAIN');classes=docs[0]['classes'];width=len(classes)
    rows=[]
    for i,target in enumerate(docs[0]['targets']):
        row=values[i*width:(i+1)*width];rows.append(dict(node_id=target,probability_units=row,probabilities=[v/scale for v in row],predicted_class=classes[max(range(width),key=lambda j:row[j])],probability_sum=sum(row)/scale))
    result=dict(status='AUTHORIZED_TARGET_PROBABILITIES',request_id=docs[0]['request_id'],model_id=docs[0]['model_id'],receiver_id=receiver_id,classes=classes,fraction=docs[0]['fraction'],results=rows,privacy='Public target IDs; only authorized final probabilities restored; full-graph propagation internally')
    result['receiver_seconds']=time.perf_counter()-started
    private_write(directory/'result.json',result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--receiver',default='local-authorized-recipient');a=p.parse_args();print(json.dumps(receive(a.directory,a.receiver),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
