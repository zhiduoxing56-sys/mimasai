"""Offline public-summary projections and strict runtime schemas.

The page only validates prebuilt UI assets. Historical reports are opened by
scripts/build_demo_assets.py in the operator workspace, never by the page.
"""
import math
from .mpc import require

CLASSES=('Case_Based','Genetic_Algorithms','Neural_Networks','Probabilistic_Methods','Reinforcement_Learning','Rule_Learning','Theory')
ROLES=('s0','s1','dealer','receiver','coordinator','page')
METRICS=('count','accuracy','macro_precision','macro_recall','macro_f1','classes')
COST=('wall_seconds','wire_bytes','rounds')

def fields(value,names):require(isinstance(value,dict) and set(value)==set(names),'DISPLAY_ASSET_FIELDS')
def integer(v,lo=0,hi=10**20):require(type(v) is int and lo<=v<=hi,'DISPLAY_ASSET_INTEGER')
def number(v,lo=0,hi=10**20):require(type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi,'DISPLAY_ASSET_NUMBER')
def identifier(v,length=32):require(isinstance(v,str) and len(v)==length and all(c in '0123456789abcdef' for c in v),'DISPLAY_ASSET_IDENTIFIER')
def boolean(v):require(type(v) is bool,'DISPLAY_ASSET_BOOLEAN')
def sources(rows):
    require(isinstance(rows,list) and rows,'DISPLAY_ASSET_SOURCES')
    for row in rows:
        fields(row,('report','sha256'));require(row['report'] in ('representative','storage_delivery','real_uid','query_success','query_failure','independence'),'DISPLAY_ASSET_SOURCE');identifier(row['sha256'],64)

def metric(value):
    """Drop confusion matrices, per-node outputs and unreviewed nested fields."""
    return dict(count=value['count'],**{k:value[k] for k in METRICS[1:-1]},classes=[{k:row[k] for k in ('class_index','support','recall')} for row in value['classes']])
def validate_metric(v):
    fields(v,METRICS);integer(v['count'],1,64)
    for k in METRICS[1:-1]:number(v[k],0,1)
    require(isinstance(v['classes'],list) and len(v['classes'])==7,'DISPLAY_ASSET_CLASSES')
    for i,row in enumerate(v['classes']):
        fields(row,('class_index','support','recall'));require(row['class_index']==i,'DISPLAY_ASSET_CLASS_ORDER');integer(row['support'],0,64);number(row['recall'],0,1)
    require(sum(row['support'] for row in v['classes'])==v['count'],'DISPLAY_ASSET_SUPPORT')
def split_metrics(value):return {k:metric(value[k]) for k in ('train','validation','test')}
def validate_splits(v):
    fields(v,('train','validation','test'))
    for name,count in (('train',28),('validation',14),('test',22)):
        validate_metric(v[name]);require(v[name]['count']==count,'DISPLAY_ASSET_SPLIT')

def training_summary(representative,control,public,digests):
    training=representative['actual_training'];effects=representative['actual_application']['effects']
    require(control['label_names']==list(CLASSES) and public['classes']==list(CLASSES),'DISPLAY_TRAINING_CLASS_ORDER')
    require(training['status']=='SHARED_TRAINING_PASS' and training['steps']==160 and representative['actual_application']['model_id']==public['model_id'],'DISPLAY_TRAINING_BINDING')
    rows=[]
    for kind,source,iterations,rate in (('word_matched','word_matched_160',160,0.5),('gcn_float','gcn_float_existing_160',160,0.5),('word_selected','word_validation_selected',control['word_selection']['iterations'],control['word_selection']['learning_rate'])):
        for row in control[source]:rows.append(dict(kind=kind,seed=row['seed'],iterations=iterations,hidden=6,learning_rate=rate,metrics=split_metrics(row['metrics'])))
    free=[]
    for row in control['label_free_existing_reference']:
        selected=next(v for v in row['curves'] if v['mode']=='float' and v['iteration']==160);top=row['topology']
        free.append(dict(strategy=row['strategy'],seed=row['sampling_seed'],nodes=top['nodes'],edge_pairs=top['unique_pairs'],isolated=top['isolated_without_added_loops'],test=metric(selected['metrics']['test'])))
    result=dict(schema='demo-training-summary-v1',model_id=public['model_id'],classes=list(CLASSES),nodes=64,dimensions=public['dimensions'],sampling=public['sampling'],seed=public['sampling_seed'],
        actual=dict(iterations=160,hidden=6,learning_rate=0.5,metrics=split_metrics(effects['published_model_metrics']),first_loss=training['first_loss'],last_preupdate_loss=training['last_preupdate_loss'],
            loss_curve=[{k:r[k] for k in ('iteration','preupdate_loss')} for r in training.get('loss_curve',[])],
            checkpoints=[dict(iteration=r['iteration'],metrics=split_metrics(r['metrics'])) for r in representative['actual_checkpoint_metrics']['records']]),
        selection=dict(reference_budget=control['frozen_gcn']['iterations'],hidden=control['frozen_gcn']['hidden'],learning_rate=control['frozen_gcn']['learning_rate'],test_used=control['word_selection']['test_used'],post_hoc_control=control['post_hoc_control'],no_test_resampling=control['no_test_driven_resampling']),
        comparisons=rows,label_free=free,sources=digests)
    validate_training(result);return result

def validate_training(v):
    fields(v,('schema','model_id','classes','nodes','dimensions','sampling','seed','actual','selection','comparisons','label_free','sources'))
    require(v['schema']=='demo-training-summary-v1' and v['classes']==list(CLASSES) and v['nodes']==64 and v['dimensions']==[64,551,6,7] and v['sampling']=='stratified_frontier' and v['seed']==20261005,'DISPLAY_TRAINING_SCOPE');identifier(v['model_id']);sources(v['sources'])
    a=v['actual'];fields(a,('iterations','hidden','learning_rate','metrics','first_loss','last_preupdate_loss','loss_curve','checkpoints'))
    require(a['iterations']==160 and a['hidden']==6 and a['learning_rate']==0.5,'DISPLAY_TRAINING_CONDITIONS');validate_splits(a['metrics']);number(a['first_loss']);number(a['last_preupdate_loss'])
    require(isinstance(a['loss_curve'],list) and len(a['loss_curve']) in (0,160),'DISPLAY_TRAINING_CURVE')
    for i,r in enumerate(a['loss_curve']):fields(r,('iteration','preupdate_loss'));require(r['iteration']==i,'DISPLAY_TRAINING_CURVE');number(r['preupdate_loss'])
    require(isinstance(a['checkpoints'],list) and a['checkpoints'],'DISPLAY_CHECKPOINTS')
    for r in a['checkpoints']:fields(r,('iteration','metrics'));integer(r['iteration'],0,160);validate_splits(r['metrics'])
    s=v['selection'];fields(s,('reference_budget','hidden','learning_rate','test_used','post_hoc_control','no_test_resampling'))
    require(s['reference_budget']==320 and s['hidden']==6 and s['learning_rate']==0.5 and s['test_used'] is False and s['post_hoc_control'] is True and s['no_test_resampling'] is True,'DISPLAY_SELECTION')
    require(isinstance(v['comparisons'],list) and len(v['comparisons'])==9,'DISPLAY_COMPARISONS')
    for r in v['comparisons']:
        fields(r,('kind','seed','iterations','hidden','learning_rate','metrics'));require(r['kind'] in ('word_matched','gcn_float','word_selected') and r['seed'] in (20261005,20261006,20261007),'DISPLAY_COMPARISON_CONDITIONS');integer(r['iterations'],1,640);require(r['hidden']==6,'DISPLAY_COMPARISON_WIDTH');number(r['learning_rate'],0,1);validate_splits(r['metrics'])
        require((r['iterations'],r['learning_rate'])==((640,0.25) if r['kind']=='word_selected' else (160,0.5)),'DISPLAY_COMPARISON_CONDITIONS')
    require(isinstance(v['label_free'],list) and len(v['label_free'])==6,'DISPLAY_LABEL_FREE')
    for r in v['label_free']:
        fields(r,('strategy','seed','nodes','edge_pairs','isolated','test'));require(r['strategy'] in ('uniform','multi_start') and r['seed'] in (20261005,20261006,20261007) and r['nodes']==64,'DISPLAY_LABEL_FREE_SCOPE');integer(r['edge_pairs'],0,4096);integer(r['isolated'],0,64);validate_metric(r['test'])
    return v

def cost(v):return {k:v.get(k) for k in COST}
def validate_cost(v):
    fields(v,COST)
    for x in v.values():
        if x is not None:number(x)

def safety_summary(matrix,success,failure,independence,digests):
    require(matrix['status']=='PASS_REAL_UID_MATRIX' and independence['status']=='PASS_REAL_NEW_MATERIALS','DISPLAY_ACCEPTANCE_STATUS')
    require(matrix['source_sha256']=='cf7da5b3c1929bbc299a7ad1a688035d4ba88643e453fed8b43add54dd972509','DISPLAY_ACCEPTANCE_SOURCE_BINDING')
    require(success['result']['delivery_state']=='complete' and failure['result']['delivery_state']=='incomplete' and failure['result']['result'] is None,'DISPLAY_ACCEPTANCE_DELIVERY')
    rows=[];cleanup=[]
    for kind,query in (('success',success),('failure',failure)):
        value=query['result'];proof=query['backend_evidence'];observation=next(r['observation'] for r in proof['lifecycle'] if r['stage']=='cleanup_observation')
        rows.append(dict(kind=kind,request_id=query['request_id'],phase=value['phase'],delivery_state=value['delivery_state'],has_result=value['result'] is not None,error=value['error'],cost=cost(value['cost']),state=proof['state'],reuse_rejected=query['post_cleanup_reuse']['rejected']))
        cleanup.append(dict(kind=kind,**{k:observation[k] for k in ('removed_files','deleted_file_allocated_bytes','unlinked_last_link_allocated_bytes','reclaimable_upper_bytes')},space_before={k:observation['space_before'][k] for k in ('internal_available_bytes','host_available_bytes','host_status')},space_after={k:observation['space_after'][k] for k in ('internal_available_bytes','host_available_bytes','host_status')}))
    result=dict(schema='demo-safety-summary-v1',audit=dict(runtime_commit='e7e5436ad69167b86440db9f171444c5c50c88fe',source_sha256=matrix['source_sha256'],timestamp_ns=matrix['timestamp_ns'],
        roles=[dict(role=r['role'],uid=r['uid'],checks=len(r['checks']),passed=sum(c['pass_check'] for c in r['checks'])) for r in matrix['roles']],
        startup_fds_closed=all(set(r['startup_fds'])=={'0','1','2'} for r in matrix['roles']),cross_secret_role_aliases=matrix['hardlink_audit']['cross_secret_role_aliases']),
        requests=rows,cleanup=cleanup,independence={k:independence[k] for k in ('distinct_batches','ring_material_ids_disjoint','he_mask_ids_disjoint','protocol_rerun')},sources=digests)
    validate_safety(result);return result

def validate_safety(v):
    fields(v,('schema','audit','requests','cleanup','independence','sources'));require(v['schema']=='demo-safety-summary-v1','DISPLAY_SAFETY_SCHEMA');sources(v['sources'])
    a=v['audit'];fields(a,('runtime_commit','source_sha256','timestamp_ns','roles','startup_fds_closed','cross_secret_role_aliases'));identifier(a['runtime_commit'],40);identifier(a['source_sha256'],64);integer(a['timestamp_ns']);boolean(a['startup_fds_closed']);integer(a['cross_secret_role_aliases'])
    require([r['role'] for r in a['roles']]==list(ROLES),'DISPLAY_ROLE_ORDER')
    for r in a['roles']:fields(r,('role','uid','checks','passed'));integer(r['uid'],1,65535);integer(r['checks'],1,1000);require(r['passed']==r['checks'],'DISPLAY_ROLE_PASS')
    require(len({r['uid'] for r in a['roles']})==6 and a['startup_fds_closed'] and a['cross_secret_role_aliases']==0,'DISPLAY_ROLE_SEPARATION')
    require(isinstance(v['requests'],list) and len(v['requests'])==2,'DISPLAY_ACCEPTANCE_REQUESTS')
    for r,kind in zip(v['requests'],('success','failure')):
        fields(r,('kind','request_id','phase','delivery_state','has_result','error','cost','state','reuse_rejected'));identifier(r['request_id']);validate_cost(r['cost']);require(r['kind']==kind and r['state']=='cleaned' and r['reuse_rejected'] is True,'DISPLAY_ACCEPTANCE_REQUEST')
        require((r['phase'],r['delivery_state'],r['has_result'],r['error'])==(('complete','complete',True,None) if kind=='success' else ('failed','incomplete',False,'INJECTED_INPUT_PREPARATION_FAILURE')),'DISPLAY_ACCEPTANCE_RESULT')
    require(isinstance(v['cleanup'],list) and len(v['cleanup'])==2,'DISPLAY_CLEANUP')
    for r,kind in zip(v['cleanup'],('success','failure')):
        fields(r,('kind','removed_files','deleted_file_allocated_bytes','unlinked_last_link_allocated_bytes','reclaimable_upper_bytes','space_before','space_after'));require(r['kind']==kind,'DISPLAY_CLEANUP_KIND')
        for key in ('removed_files','deleted_file_allocated_bytes','unlinked_last_link_allocated_bytes','reclaimable_upper_bytes'):integer(r[key])
        for key in ('space_before','space_after'):
            s=r[key];fields(s,('internal_available_bytes','host_available_bytes','host_status'));integer(s['internal_available_bytes']);require(s['host_status'] in ('READABLE','UNKNOWN'),'DISPLAY_SPACE_STATUS')
            if s['host_status']=='READABLE':integer(s['host_available_bytes'])
            else:require(s['host_available_bytes'] is None,'DISPLAY_HOST_UNKNOWN')
    i=v['independence'];fields(i,('distinct_batches','ring_material_ids_disjoint','he_mask_ids_disjoint','protocol_rerun'));require(i['distinct_batches'] is True and i['ring_material_ids_disjoint'] is True and i['he_mask_ids_disjoint'] is True and i['protocol_rerun'] is False,'DISPLAY_NEW_MATERIALS')
    return v
