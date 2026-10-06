"""The web contract contains public model metadata and authorized final results."""
import math
from .mpc import require

def planning_report(report):
    """Only public fields required to bind the existing inference plan.

    Never install historical worker metrics/message traces as shared config.
    """
    publication=report['publication']
    return dict(experiment_id=report['experiment_id'],nodes=report['nodes'],dimensions=report['dimensions'],
        allowed_targets=report['allowed_targets'],receiver_id=report['receiver_id'],
        data={k:report['data'].get(k) for k in ('sampling','sampling_seed')},
        publication={k:publication[k] for k in ('models','session','source_training_session','source_training_iteration')},
        he_setup=dict(public=report['he_setup']['public']))

def model(report):
    publication=report['publication'];binding=publication['models'][-1]
    require(report['nodes']==64 and publication['source_training_iteration']==160,'DEMO_FIXED_SCOPE')
    return dict(experiment_id=report['experiment_id'],model_id=binding['model_id'],
        source_training_session=publication['source_training_session'],source_iteration=160,
        nodes=64,dimensions=report['dimensions'],sampling=report['data'].get('sampling'),
        sampling_seed=report['data'].get('sampling_seed'),allowed_targets=report['allowed_targets'],
        receiver_id=report['receiver_id'],classes=binding['class_order'],
        scope='固定64节点诱导图；已有160轮发布模型；两方半诚实及可信离线方',
        protocol='真实 SEAL / 私有解密转换 / FSS / 最终概率份额')

def final(doc,public,sid):
    require(doc['status']=='AUTHORIZED_TARGET_PROBABILITIES' and doc['request_id']==sid and
        doc['model_id']==public['model_id'] and doc['receiver_id']==public['receiver_id'] and doc['classes']==public['classes'],'PUBLIC_FINAL_BINDING')
    rows=[]
    require([r['node_id'] for r in doc['results']]==public['allowed_targets'],'PUBLIC_FINAL_TARGETS')
    for row in doc['results']:
        values=row['probabilities'];require(len(values)==len(public['classes']) and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in values),'PUBLIC_PROBABILITIES')
        require(row['predicted_class']==public['classes'][max(range(len(values)),key=lambda j:values[j])],'PUBLIC_PREDICTION')
        rows.append(dict(node_id=row['node_id'],probabilities=values,predicted_class=row['predicted_class'],probability_sum=sum(values)))
    return dict(request_id=sid,model_id=public['model_id'],classes=public['classes'],results=rows)

def status(value,public):
    """Recursive public allowlist; extra backend fields never cross to HTTP."""
    phases={'admission','offline','input','online','export','receiver','complete','failed','stopping'}
    require(value['phase'] in phases and type(value['terminal']) is bool and value['delivery_state'] in ('pending','complete','incomplete'),'PUBLIC_STATE')
    from .deployment import hexid
    sid=hexid(value['request_id']);result=None
    if value['result'] is not None:
        require(value['terminal'] and value['phase']=='complete' and value['delivery_state']=='complete','PUBLIC_INCOMPLETE_RESULT')
        result=final(dict(value['result'],status='AUTHORIZED_TARGET_PROBABILITIES',receiver_id=public['receiver_id']),public,sid)
    require(value['delivery_state']!='complete' or result is not None,'PUBLIC_MISSING_RESULT')
    cost=None
    if value['cost'] is not None:
        cost={key:value['cost'].get(key) for key in ('wall_seconds','wire_bytes','rounds')}
        require(all(v is None or type(v) in (int,float) and math.isfinite(v) and v>=0 for v in cost.values()),'PUBLIC_COST')
    error=value['error'];require(error is None or isinstance(error,str) and error and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in error),'PUBLIC_ERROR')
    return dict(request_id=sid,phase=value['phase'],terminal=value['terminal'],delivery_state=value['delivery_state'],result=result,cost=cost,error=error)
