"""Executable stage-one checks; all training and reconstruction are plaintext tests."""
import copy
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import *

OUT=ROOT/'results/stage1'
OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def reject(fn,exc=ValueError):
    try: fn()
    except exc: return True
    raise AssertionError('expected rejection')
def error(a,b): return max(abs(x-y) for row,col in zip(a,b) for x,y in zip(row,col))
def main():
    c=config(); g=c['graph_reference']; m=c['model_reference']; a,d,p=graph(g); x=g['features']; w=copy.deepcopy(m['initial_weights'])
    assert a[0][1]==1 and a[4][4]==1 and d==[2,5,2,3,1]
    bad=[]
    for edge in ([0,0,1],[0,1,-1],[0,5,1],[0,1,float('nan')],[0,1],[0.5,1,1]):
        gg=copy.deepcopy(g); gg['undirected_edges']=[edge]; bad.append(reject(lambda:graph(gg)))
    loss,grad,initial=loss_grad(p,x,w,m['labels'],m['training_mask'])
    minmargin=min(abs(v) for row in initial['activation_input'] for v in row)
    assert minmargin>100*m['gradient_epsilon']
    checks=[]
    for l in range(2):
        for i,row in enumerate(w[l]):
            for j,_ in enumerate(row):
                plus=copy.deepcopy(w); minus=copy.deepcopy(w); eps=m['gradient_epsilon']
                plus[l][i][j]+=eps; minus[l][i][j]-=eps
                # Independent probability/log loss; analytic path uses stable log-sum-exp.
                def numerical_loss(weights):
                    probs=forward(p,x,weights)['probabilities']
                    return -sum(math.log(probs[t][m['labels'][t]]) for t,on in enumerate(m['training_mask']) if on)/sum(m['training_mask'])
                numeric=(numerical_loss(plus)-numerical_loss(minus))/(2*eps)
                checks.append(dict(layer=l,row=i,col=j,analytic=grad[l][i][j],numeric=numeric,absolute_error=abs(numeric-grad[l][i][j])))
    assert max(v['absolute_error'] for v in checks)<1e-8
    # Mask changes only the loss contributions, never the graph propagation.
    assert reject(lambda:loss_grad(p,x,w,m['labels'],[[True]]*5))
    assert reject(lambda:loss_grad(p,x,w,m['labels'],[False]*5))
    masked_labels=m['labels'][:]; masked_labels[4]=1
    assert loss_grad(p,x,w,masked_labels,m['training_mask'])[0]==loss
    assert initial['logit_gradient'][4]==[0,0]
    history=[]
    for iteration in range(m['iterations']):
        ll,gg,ff=loss_grad(p,x,w,m['labels'],m['training_mask']); history.append(ll)
        w=[[[v-m['learning_rate']*dv for v,dv in zip(row,dr)] for row,dr in zip(layer,dl)] for layer,dl in zip(w,gg)]
    final_loss,final_grad,final=loss_grad(p,x,w,m['labels'],m['training_mask'])
    assert final_loss<loss*0.8
    write('initial-trace.json',initial); write('trained-trace.json',final); write('gradient-check.json',checks)
    save_model(OUT/'model-reference.json',w,c); loaded=load_model(OUT/'model-reference.json',c)
    assert forward(p,x,loaded)==forward(p,x,w)
    wrong=copy.deepcopy(c); wrong['model_reference']['bias']='trainable'
    assert reject(lambda:load_model(OUT/'model-reference.json',wrong))
    damaged=json.loads((OUT/'model-reference.json').read_text()); damaged['weights'][0][0][0]+=0.1
    write('tampered-model-test.json',damaged)
    assert reject(lambda:load_model(OUT/'tampered-model-test.json',c))
    fixed=Fixed(c); qp=fixed.encode(p); qx=fixed.encode(x); qw=[fixed.encode(layer) for layer in w]
    write('quantized-inputs.json',dict(propagation=qp,features=qx,weights=qw,scale=fixed.scale))
    tf=fixed.forward(qp,qx,qw,'transform_then_aggregate')
    afixed=Fixed(c); af=afixed.forward(qp,qx,qw,'aggregate_then_transform')
    write('fixed-transform-first.json',tf); write('fixed-aggregate-first.json',af)
    compare={}
    for key in ['activation_input','hidden','logits']:
        compare[key]={'float_fixed_max_abs':error(final[key],fixed.decode(tf[key])),'path_difference_integer_units':max(abs(fixed.signed(u)-fixed.signed(v)) for row,col in zip(tf[key],af[key]) for u,v in zip(row,col))}
    fp=[[float(v) for v in row] for row in tf['probabilities']]
    assert any(entry['path_difference_integer_units']>0 for entry in compare.values())
    compare['probabilities']={'max_abs_error':error(final['probabilities'],fp),'class_agreement':[max(range(m['classes']),key=lambda j:fr[j])==max(range(m['classes']),key=lambda j:qr[j]) for fr,qr in zip(final['probabilities'],fp)]}
    compare['activation_ranges']={'float':[min(v for row in final['activation_input'] for v in row),max(v for row in final['activation_input'] for v in row)],'fixed_signed_integer':[min(fixed.signed(v) for row in tf['activation_input'] for v in row),max(fixed.signed(v) for row in tf['activation_input'] for v in row)]}
    hp=precise_softmax(final['logits']); assert error(final['probabilities'],[[float(v) for v in row] for row in hp])<1e-14
    write('high-precision-float-probabilities.json',hp)
    # Overflow and numerical boundary regressions; no wrapping accepted.
    boundary=Fixed(c)
    assert boundary.signed((1<<32)-1)==-1
    assert boundary.checked(-(1<<31),'negative endpoint')==-(1<<31)
    assert reject(lambda:boundary.checked(1<<31,'positive endpoint'),OverflowError)
    assert boundary.encode([[0.5/128,1.5/128,-0.5/128,-1.5/128]])==[[0,2,0,(1<<32)-2]]
    assert boundary.signed(boundary.mul([[(-1)%(1<<32)]],[[1]],'negative_floor')[0][0])==-1
    assert reject(lambda:boundary.encode([[float('inf')]]),OverflowError)
    assert reject(lambda:boundary.encode([[2**24]]),OverflowError)
    assert reject(lambda:boundary.mul([[50000]],[[50000]],'product_overflow'),OverflowError)
    assert reject(lambda:boundary.mul([[40000,40000]],[[40000],[40000]],'sum_overflow'),OverflowError)
    pair=split_test(qw,c)
    for file,data in zip(['S0-shares.json','S1-shares.json'],pair): write(file,data)
    persisted=[json.loads((OUT/file).read_text()) for file in ['S0-shares.json','S1-shares.json']]
    assert recover_test(persisted,c)==qw
    refreshed=refresh_test(persisted,c)
    for file,data in zip(['S0-refreshed.json','S1-refreshed.json'],refreshed): write(file,data)
    reread=[json.loads((OUT/file).read_text()) for file in ['S0-refreshed.json','S1-refreshed.json']]
    assert recover_test(reread,c)==qw
    assert reject(lambda:recover_test([pair[0],refreshed[1]],c))
    assert reject(lambda:recover_test([pair[1],pair[0]],c))
    target=select_targets(final['probabilities'],['isolated','n0'],g['node_order'])
    assert target==[final['probabilities'][4],final['probabilities'][0]]
    assert reject(lambda:select_targets(final['probabilities'],['absent'],g['node_order']))
    conv=m['convergence']; assert convergence([0.1,0,0,0],**conv)=={'stop':True,'iteration':4,'reason':'threshold_window'}
    assert convergence([conv['threshold']]*3,**conv)['reason']=='threshold_window'
    assert convergence([0,0,1,0,0],**conv)['reason']=='continue'
    assert convergence([1]*conv['max_iterations'],**conv)['reason']=='max_iterations'
    assert softmax([[1000,999],[-1000,-999]])[0][0]>0.5
    # Integrate suggested activation with actual trained range, selecting k from the observed test fixture only.
    vals=[fixed.signed(v) for row in tf['activation_input'] for v in row]
    k=next(k for k in range(2,c['ring_bits']) if all(-(1<<(k-1))<=v<(1<<(k-1)) for v in vals))
    for v in vals:
        for mask in [0,1,(1<<32)-1,1<<31]:
            for rb in (0,1):
                result=corrected_activation(v,32,k,mask,rb,0,1)
                assert result['nonnegative']==int(v>=0) and result['relu']==max(0,v)
    assert reject(lambda:corrected_activation(1<<(k-1),32,k,0,0,0,0))
    summary=dict(status='PASS_PLAINTEXT_REFERENCE_ONLY',initial_loss=loss,final_loss=final_loss,iterations=m['iterations'],gradient_max_abs_error=max(v['absolute_error'] for v in checks),gradient_min_relu_margin=minmargin,graph_degrees=d,invalid_graph_cases_rejected=len(bad),comparison=compare,overflow_checks='PASS: encoding, product, partial accumulation rejected',model_save_load='exact output equality; binding/hash mismatch rejected',share_persistence_refresh='PASS independent reconstruction tests only; mixed generation rejected',convergence='PASS <= threshold, equality, consecutive reset, max limit',activation_model_fixture=dict(observed_k=k,cases=len(vals)*8,outside_range='rejected',scope='truth-table algebra only; not universal certified range'),training_history=history)
    write('summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='training_history'},indent=2))
if __name__=='__main__': main()
