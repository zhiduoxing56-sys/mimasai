"""Full Cora owner-only floating/fixed experiment, never a secure-compute claim."""
import copy,json,random,resource,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data import cora
from src.reference import config,Fixed,loss_grad,graph,ROOT
from src.numerical import training_reference,probability_reference
from src.sparse_reference import sparse,step
from verification.real_data import accuracy

def main():
 c=config();cc=copy.deepcopy(c);cc['fraction_bits']=c['training_reference']['fraction_bits'];cc['training_reference']['loss_mode']='range_reduced';fx=Fixed(cc)
 # Independent dense-vs-sparse full forward, gradients and update regression.
 small=cora();rng=random.Random(c['data_experiment']['initialization_seed']);f=len(small['features'][0]);h=c['model_reference']['hidden_width'];classes=7;ww=[[[rng.gauss(0,.2) for j in range(h)] for i in range(f)],[[rng.gauss(0,.2) for j in range(classes)] for i in range(h)]];mask=[i in small['splits']['train'] for i in range(16)];P=fx.encode(small['propagation']);X=fx.encode(small['features']);W=[fx.encode(v) for v in ww];dense,nw,_=training_reference(P,X,W,small['labels'],mask,cc);dec=lambda a:[[fx.signed(v) for v in row] for row in a];sp,snw,_=step(sparse(dec(P)),sparse(dec(X)),[dec(v) for v in W],small['labels'],mask,fx,c['model_reference']['learning_rate']);flat=lambda a:[v%fx.mod for row in a for v in row]
 for key,value in dense.items():assert value==([sp[key]] if key=='loss' else flat(sp[key][0])+flat(sp[key][1]) if key=='next_weights' else flat(sp[key])),key
 floatloss,fg,_=loss_grad(small['propagation'],small['features'],ww,small['labels'],mask);spfloat,_,_=step(sparse(small['propagation']),sparse(small['features']),ww,small['labels'],mask,learning_rate=c['model_reference']['learning_rate']);assert abs(floatloss-spfloat['loss'])<1e-12;assert max(abs(a-b) for aa,bb in zip(fg,[spfloat['gradient0'],spfloat['gradient1']]) for row,rr in zip(aa,bb) for a,b in zip(row,rr))<1e-12
 data=cora(full_graph=True);n=len(data['features']);features=len(data['feature_columns']);rng=random.Random(c['data_experiment']['initialization_seed']);w=[[[rng.gauss(0,.2) for j in range(h)] for i in range(features)],[[rng.gauss(0,.2) for j in range(classes)] for i in range(h)]];fw=[[[round(v*fx.scale) for v in row] for row in layer] for layer in w];p=data['propagation'];x=sparse(data['features']);pf=[[(j,round(v*fx.scale)) for j,v in row if round(v*fx.scale)] for row in p];xf=[[(j,round(v*fx.scale)) for j,v in row] for row in x];mask=[i in data['splits']['train'] for i in range(n)];curve=[];ranges=[];started=time.perf_counter();fixed_failure=None;first_protocol_policy_violation=None;best_validation=(-1,None,0);out=ROOT/'results/real-data/full-reference.json';out.parent.mkdir(parents=True,exist_ok=True)
 for it in range(c['data_experiment']['maximum_full_reference_iterations']):
  tr,w,_=step(p,x,w,data['labels'],mask,learning_rate=c['model_reference']['learning_rate']);entry=dict(iteration=it,float_loss=tr['loss'],float_train_accuracy=accuracy(tr['probabilities'],data['labels'],data['splits']['train']),float_validation_accuracy=accuracy(tr['probabilities'],data['labels'],data['splits']['validation']))
  if entry['float_validation_accuracy']>best_validation[0]:best_validation=(entry['float_validation_accuracy'],[row[:] for row in tr['probabilities']],it)
  if fixed_failure is None:
   try:
    fr,fw,audit=step(pf,xf,fw,data['labels'],mask,fx,c['model_reference']['learning_rate'])
    groups={'transform0':'state','activation_input':'state','hidden':'state','transform1':'state','logits':'score','backprop1':'backprop_state','backprop_hidden':'state','backprop0':'state','gradient0':'gradient','gradient1':'gradient'}
    for key,role in groups.items():
     bound=fx.scale*2**c['range_policy']['operand_bound_exponents'][role];values=[v for row in fr[key] for v in row]
     if first_protocol_policy_violation is None and any(v< -bound or v>=bound for v in values):first_protocol_policy_violation=dict(iteration=it,group=key,min_units=min(values),max_units=max(values),bound_units=bound)
    entry.update(fixed_loss=fr['loss']/fx.scale,fixed_train_accuracy=accuracy(fr['probabilities'],data['labels'],data['splits']['train']),fixed_validation_accuracy=accuracy(fr['probabilities'],data['labels'],data['splits']['validation']),probability_max_error=max(abs(a/fx.scale-b) for aa,bb in zip(fr['probabilities'],tr['probabilities']) for a,b in zip(aa,bb)));ranges.extend(dict(iteration=it,**a) for a in audit)
   except (ValueError,OverflowError) as e:
    from src.sparse_reference import multiply
    t0=multiply(xf,sparse(fw[0]),h,fx);z0=multiply(pf,sparse(t0),h,fx);hidden=[[max(0,v) for v in row] for row in z0];t1=multiply(sparse(hidden),sparse(fw[1]),classes,fx);scores=multiply(pf,sparse(t1),classes,fx);badprob,ex=probability_reference(scores,cc['fraction_bits']);zeros=[dict(node=data['node_order'][i],label=data['labels'][i],target_probability_units=badprob[i][data['labels'][i]],logits=scores[i],exponential=ex[i]['exponential'],denominator=ex[i]['denominator']) for i in range(n) if mask[i] and badprob[i][data['labels'][i]]==0];fixed_failure=dict(iteration=it,reason=str(e),zero_target_cases=zeros)
  curve.append(entry)
  if it%20==0:print(json.dumps(entry),flush=True)
 # Test evaluated once at the fixed end budget; no test-driven selection.
 tr,_,_=step(p,x,w,data['labels'],mask,learning_rate=c['model_reference']['learning_rate']);float_test=accuracy(best_validation[1],data['labels'],data['splits']['test']);fixed_test=None
 if fixed_failure is None:fr,_,_=step(pf,xf,fw,data['labels'],mask,fx,c['model_reference']['learning_rate']);fixed_test=accuracy(fr['probabilities'],data['labels'],data['splits']['test'])
 from collections import Counter
 majority=Counter(data['labels'][i] for i in data['splits']['train']).most_common(1)[0][0];majority_test=sum(data['labels'][i]==majority for i in data['splits']['test'])/len(data['splits']['test'])
 result=dict(status='PASS_FULL_CORA_PLAINTEXT_REFERENCE' if fixed_failure is None else 'FULL_CORA_FIXED_REFERENCE_BLOCKED',dimensions=[n,features,h,classes],curve=curve,ranges=ranges,float_test_accuracy=float_test,float_validation_selected_iteration=best_validation[2],float_validation_selected_accuracy=best_validation[0],fixed_test_accuracy=fixed_test,training_majority_class=majority,majority_test_accuracy=majority_test,fixed_failure=fixed_failure,seconds=time.perf_counter()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,first_protocol_operand_policy_violation=first_protocol_policy_violation,dense_sparse_gradient_regression=True,data={k:v for k,v in data.items() if k not in ('features','propagation','labels','edges')},scope='Full original Cora graph, self-written plaintext references only; no secure full-graph training, approximate standard p-y gradient');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('status','dimensions','float_test_accuracy','fixed_test_accuracy','majority_test_accuracy','seconds','fixed_failure')},indent=2))
if __name__=='__main__':main()
