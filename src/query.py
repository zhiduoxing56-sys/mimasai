"""Public local authorization policy and final-only server delivery, no recovery."""
from .model import validate
from .mpc import require

def validate_delivery(job,authorization=None):
    policy=job['delivery']
    require(set(policy)=={'model','targets','receiver_id','request_id'},'QUERY_POLICY_FIELDS')
    validate(policy['model'])
    require(isinstance(policy['receiver_id'],str) and policy['receiver_id'] and policy['request_id']==job['session'],'QUERY_RECEIVER_BINDING')
    targets=policy['targets'];nodes=policy['model']['node_order']
    require(isinstance(targets,list) and targets and len(set(targets))==len(targets) and all(v in nodes for v in targets),'QUERY_TARGETS')
    if authorization is not None:
        require(set(authorization)=={'model','allowed_targets','receiver_id'} and authorization['model']==policy['model'] and authorization['receiver_id']==policy['receiver_id'],'QUERY_AUTHORIZATION')
        require(all(v in authorization['allowed_targets'] for v in targets),'QUERY_UNAUTHORIZED_TARGET')
    ops=job['operations']
    require(ops and ops[-1]['type']=='deliver' and all(op['type']!='deliver' for op in ops[:-1]),'QUERY_FINAL_DELIVERY')
    final=ops[-1];classes=policy['model']['dimensions'][2]
    require(final.get('targets')==targets and final.get('receiver_id')==policy['receiver_id'] and final.get('model')==policy['model'],'QUERY_AUTHORIZATION')
    require(final.get('dims')==[len(nodes),classes] and final.get('use_previous') is True and 'previous_slice' not in final,'QUERY_OUTPUT_SHAPE')
    require(len(ops)>1 and ops[-2]['type']=='probability' and ops[-2]['dims']==final['dims'] and ops[-2]['fraction']==policy['model']['probability_fraction_bits'],'QUERY_PROBABILITY_REQUIRED')
    # Every model-bearing computation is bound to the authorized model.
    require(all(op.get('model',policy['model'])==policy['model'] for op in ops),'QUERY_MODEL_BINDING')

def select_result(job,op,values,index):
    validate_delivery(job)
    require(index==len(job['operations'])-1,'QUERY_FINAL_DELIVERY')
    nodes=op['model']['node_order'];classes=op['dims'][1]
    require(len(values)==len(nodes)*classes,'QUERY_OUTPUT_SHAPE')
    return [values[nodes.index(target)*classes+j] for target in op['targets'] for j in range(classes)]
